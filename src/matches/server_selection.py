from math import radians, cos, sin, asin, sqrt
from typing import List, Tuple, TYPE_CHECKING, Dict, cast

if TYPE_CHECKING:
    from main import Bot

from utils.models import MMBotUsers, RconServers, BotRegions

EARTH_RADIUS_KM = 6371
MS_PER_KM = 0.0168
AS_CORRECTION_THRESHOLD_KM = 350
AS_HEIGHT_REDUCTION = 0.6
TIV_THRESHOLD_MS = 100
GEOGRAPHIC_DEFAULT_UNCERTAINTY = 0.292
DEFAULT_HEIGHT_MS = 10.0

def haversine(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lon_a, lat_a, lon_b, lat_b = map(radians, [lon_a, lat_a, lon_b, lat_b])
    dlon, dlat = lon_b - lon_a, lat_b - lat_a
    a = sin(dlat / 2.)**2 + cos(lat_a) * cos(lat_b) * sin(dlon / 2.)**2
    return 2 * asin(sqrt(a)) * EARTH_RADIUS_KM


class HtraeNCS:
    @staticmethod
    async def get_server_scores(regions: List[BotRegions], users: List[MMBotUsers], servers: List[RconServers]) -> List[Tuple[RconServers, float]]:
        if not users or not servers:
            return []
            
        scored_servers = []
        
        for server in servers:
            s_coords = await HtraeNCS._get_coords(regions, server)
            
            user_scores = []
            for user in users:
                u_coords = await HtraeNCS._get_coords(regions, user)
                
                rtt = HtraeNCS._calculate_pair_rtt(u_coords, s_coords, same_as=(bool(user.region) == server.region))
                
                score = HtraeNCS._calculate_score(rtt)
                user_scores.append(score)
            
            server_score = sum(user_scores) / len(user_scores) if user_scores else -1.0
            scored_servers.append((server, server_score))
        
        return sorted(scored_servers, key=lambda x: x[1], reverse=True)

    @staticmethod
    async def _get_coords(regions: List[BotRegions], target: MMBotUsers | RconServers) -> Tuple[float, float, float, float]:
        if target.lat is not None and target.lon is not None:
            return (
                cast(float, target.lat), 
                cast(float, target.lon), 
                cast(float, target.height) or DEFAULT_HEIGHT_MS, 
                cast(float, target.uncertainty) or GEOGRAPHIC_DEFAULT_UNCERTAINTY)
        
        region = {r.label: r for r in regions}.get(target.region)
        if region and region.base_latitude is not None and region.base_longitude is not None:
            return (
                cast(float, region.base_latitude), 
                cast(float, region.base_longitude), 
                cast(float, region.base_height) or DEFAULT_HEIGHT_MS, 
                cast(float, target.uncertainty) or GEOGRAPHIC_DEFAULT_UNCERTAINTY)
        
        raise ValueError(
            f"Target {target.user_id if isinstance(target, MMBotUsers) else f'{target.host}:{target.port}'} "
            f"has no identifiable region or coordinates")

    @staticmethod
    def _calculate_pair_rtt(u_coords: tuple, s_coords: tuple, same_as: bool = False) -> float:
        u_lat, u_lon, u_height, u_unc = u_coords
        s_lat, s_lon, s_height, s_unc = s_coords
        
        distance = haversine(u_lat, u_lon, s_lat, s_lon)
        
        combined_height = u_height + s_height
        
        if same_as and distance < AS_CORRECTION_THRESHOLD_KM:
            combined_height *= AS_HEIGHT_REDUCTION
        
        base_rtt = (distance * MS_PER_KM) + combined_height
        
        uncertainty_factor = 1 + ((u_unc + s_unc) * 0.5)
        return base_rtt * uncertainty_factor

    @staticmethod
    def _calculate_score(rtt: float) -> float:
        if rtt <= 50:
            return 1.0  # Excellent RTT
        elif rtt >= 150:
            return -1.0  # Poor RTT
        
        return 0.5 - (rtt - 50) / 50

    @staticmethod
    async def update_coordinates(bot: "Bot", 
        regions: List[BotRegions], 
        server: RconServers, 
        user_rtts: List[Tuple[MMBotUsers, float]]
    ) -> None:
        s_coords = await HtraeNCS._get_coords(regions, server)
        user_updates: Dict[int, Tuple[float, float, float, float]] = {}
        server_deltas = []
        
        for user, rtt in user_rtts:
            if rtt <= 0: continue
            
            u_coords = await HtraeNCS._get_coords(regions, user)
            
            same_as = user.region == server.region
            predicted_rtt = HtraeNCS._calculate_pair_rtt(u_coords, s_coords, cast(bool, same_as))
        
            if (rtt > predicted_rtt + TIV_THRESHOLD_MS 
                and u_coords[3] < GEOGRAPHIC_DEFAULT_UNCERTAINTY 
                and s_coords[3] < GEOGRAPHIC_DEFAULT_UNCERTAINTY
            ):
                u_new_uncertainty = max(0.1, u_coords[3] * 0.95)
                user_updates[cast(int, user.user_id)] = (u_coords[0], u_coords[1], u_coords[2], u_new_uncertainty)
                continue
            
            u_new = HtraeNCS._adjust_coordinates(u_coords, s_coords, rtt, predicted_rtt, is_server=False)
            user_updates[cast(int, user.user_id)] = u_new
            
            s_new = HtraeNCS._adjust_coordinates(s_coords, u_coords, rtt, predicted_rtt, is_server=True)
            server_deltas.append(tuple(a - b for a, b in zip(s_new, s_coords)))
        
        if not user_updates: return
        await bot.store.update_user_coords(guild_id=user_rtts[0][0].guild_id, user_coords=user_updates)
        
        if server_deltas:
            s_avg = tuple(sum(deltas) / len(server_deltas) for deltas in zip(*server_deltas))
            await bot.store.update(RconServers, id=server.id, 
                lat=s_coords[0] + s_avg[0], 
                lon=s_coords[1] + s_avg[1], 
                height=s_coords[2] + s_avg[2], 
                uncertainty=s_coords[3] + s_avg[3])

    @staticmethod
    def _adjust_coordinates(
        source_coords: tuple, 
        target_coords: tuple, 
        measured_rtt: float,
        predicted_rtt: float,
        is_server: bool = False
    ) -> Tuple[float, float, float, float]:
        s_lat, s_lon, s_height, s_unc = source_coords
        t_lat, t_lon, _, t_unc = target_coords
        
        error = (measured_rtt - predicted_rtt) / max(1.0, measured_rtt)
        
        weight = t_unc / (s_unc + t_unc) if (s_unc + t_unc) > 0 else 0.5
        
        adjustment_rate = 0.1 if is_server else 0.9
        force_factor = error * weight * adjustment_rate
        
        distance = haversine(s_lat, s_lon, t_lat, t_lon)
        
        if distance > 0:
            lat_dir = (t_lat - s_lat) / distance
            lon_dir = (t_lon - s_lon) / distance
            
            new_lat = s_lat + lat_dir * force_factor * 5.0
            new_lon = s_lon + lon_dir * force_factor * 5.0
        else:
            new_lat = s_lat
            new_lon = s_lon
        
        new_height = s_height * (1 - error * weight * 0.1)
        new_unc = max(0.1, s_unc * (0.99 if is_server else 0.95))
        
        return (new_lat, new_lon, new_height, new_unc)


get_server_scores = HtraeNCS.get_server_scores
update_coordinates = HtraeNCS.update_coordinates
