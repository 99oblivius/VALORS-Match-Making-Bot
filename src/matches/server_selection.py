from math import radians, cos, sin, asin, sqrt
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from main import Bot

from utils.models import MMBotUsers, RconServers, BotRegions

EARTH_RADIUS_KM = 6371
MS_PER_KM = 0.0168
AS_CORRECTION_THRESHOLD_KM = 350
AS_HEIGHT_REDUCTION = 0.8
UNCERTAINTY_CE = 0.25

def haversine(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lon_a, lat_a, lon_b, lat_b = map(radians, [lon_a, lat_a, lon_b, lat_b])
    dlon, dlat = lon_b - lon_a, lat_b - lat_a
    a = sin(dlat / 2.)**2 + cos(lat_a) * cos(lat_b) * sin(dlon / 2.)**2
    return 2 * asin(sqrt(a)) * EARTH_RADIUS_KM


class HtraeNCS:
    @staticmethod
    async def get_server_scores(regions: List[BotRegions], users: List[MMBotUsers], servers: List[RconServers]) -> List[Tuple[RconServers, float]]:
        scored_servers = []
        
        for server in servers:
            s_coords = await HtraeNCS._get_coords(regions, server)
            
            user_scores = []
            for user in users:
                u_coords = await HtraeNCS._get_coords(regions, user)
                rtt = HtraeNCS._calculate_pair_rtt(u_coords, s_coords)
                
                score = HtraeNCS._calculate_score(rtt)
                user_scores.append(score)
            
            server_score = sum(user_scores) / len(user_scores)
            scored_servers.append((server, server_score))
        
        return sorted(scored_servers, key=lambda x: x[1], reverse=True)

    @staticmethod
    async def _get_coords(regions: List[BotRegions], target: MMBotUsers | RconServers) -> tuple:
        if target.lat is None or target.lon is None:
            region = { r.label: r for r in regions }.get(target.region)
            if region: return (
                region.base_latitude, 
                region.base_longitude, 
                region.base_height, 
                target.uncertainty)
            else:
                raise Exception(
f"Target {target.user_id if isinstance(target, MMBotUsers) else f'{target.host}:{target.port}'} has no identifiable region")            
        
        return (
            target.lat, 
            target.lon, 
            target.height, 
            target.uncertainty)

    @staticmethod
    def _calculate_pair_rtt(u_coords: tuple, s_coords: tuple) -> float:
        u_lat, u_lon, u_height, u_unc = u_coords
        s_lat, s_lon, s_height, s_unc = s_coords
        
        distance = haversine(u_lat, u_lon, s_lat, s_lon)
        
        combined_height = u_height + s_height
        if distance < AS_CORRECTION_THRESHOLD_KM: combined_height *= AS_HEIGHT_REDUCTION
        
        base_rtt = (distance * MS_PER_KM) + combined_height
        return base_rtt * (1 + (u_unc * 0.5 + s_unc * 0.5))

    @staticmethod
    def _calculate_score(rtt: float) -> float:
        if rtt <= 50: return 1.0
        elif rtt >= 100: return -1.0
        return 0.5 - (rtt - 50) / 50

    @staticmethod
    async def update_coordinates(bot: "Bot", regions: List[BotRegions], server: RconServers, users: List[MMBotUsers], measured_rtts: List[float]):
        if len(users) != len(measured_rtts):
            raise ValueError("Users and RTTs must have equal length")
        
        s_coords = await HtraeNCS._get_coords(regions, server)
        user_updates = {}
        server_deltas = []
        
        for user, rtt in zip(users, measured_rtts):
            if rtt <= 0: continue
            
            u_coords = await HtraeNCS._get_coords(regions, user)
            
            u_new = HtraeNCS._adjust_coordinates(u_coords, s_coords, rtt)
            user_updates[user.user_id] = u_new
            
            s_new = HtraeNCS._adjust_coordinates(s_coords, u_coords, rtt, is_server=True)
            server_deltas.append(tuple(a - b for a, b in zip(s_new, s_coords)))
        
        if not len(user_updates): return
        await bot.store.update_user_coords(guild_id=users[0].guild_id, user_coords=user_updates)
                
        s_avg = tuple(sum(deltas) / len(user_updates) for deltas in zip(*server_deltas))
        await bot.store.update(RconServers, id=server.id, 
            **{ k: val for k, val in zip(('lat','lon','height','uncertainty'), s_avg) })

    @staticmethod
    def _adjust_coordinates(
        source_coords: tuple, 
        target_coords: tuple, 
        measured_rtt: float, 
        is_server=False
    ) -> Tuple[float, float, float, float]:
        s_lat, s_lon, s_height, s_unc = source_coords
        t_lat, t_lon, _, t_unc = target_coords
        
        distance = haversine(s_lat, s_lon, t_lat, t_lon)
        predicted_rtt = (distance * MS_PER_KM) + s_height
        error = (predicted_rtt - measured_rtt) / measured_rtt

        weight = t_unc / (s_unc + t_unc)
        adjustment_rate = 0.1 if is_server else 0.9
        
        new_lat = s_lat + (t_lat - s_lat) * error * weight * adjustment_rate
        new_lon = s_lon + (t_lon - s_lon) * error * weight * adjustment_rate
        new_height = s_height * (1 - error * weight * 0.1)
        new_unc = max(0.1, s_unc * (0.1 if is_server else 0.9))

        return (new_lat, new_lon, new_height, new_unc)


get_server_scores = HtraeNCS.get_server_scores
update_coordinates = HtraeNCS.update_coordinates
