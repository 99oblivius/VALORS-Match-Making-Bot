from math import radians, cos, sin, asin, sqrt
from typing import List, Tuple, TYPE_CHECKING, Dict, cast

if TYPE_CHECKING:
    from main import Bot

from utils.models import MMBotUsers, RconServers, BotRegions

# Earth constants
EARTH_RADIUS_KM = 6371
KM_PER_DEG_LAT = 111.32

# Latency-to-distance model
MS_PER_KM = 0.012

# Vivaldi-inspired convergence parameters
CC = 0.05                      # Convergence constant (step size scaling)
CE = 0.5                       # Error smoothing constant for uncertainty
SERVER_MOVE_FACTOR = 0.1       # Servers move 10x less than users
MAX_MOVE_KM = 500.0            # Cap movement per observation

# Same-AS (same autonomous system / region) correction
AS_CORRECTION_THRESHOLD_KM = 350
AS_HEIGHT_REDUCTION = 0.8

# Bounds
MIN_HEIGHT_MS = 0.0
MAX_HEIGHT_MS = 100.0
MIN_UNCERTAINTY = 0.01
MAX_UNCERTAINTY = 1.0

# Defaults for new/reset nodes
DEFAULT_HEIGHT_MS = 10.0
DEFAULT_UNCERTAINTY = 0.5

# Triangle inequality violation threshold
TIV_THRESHOLD_MS = 100


def haversine(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance in km. Inputs in degrees. Clamped to prevent domain errors."""
    lon_a, lat_a, lon_b, lat_b = map(radians, [lon_a, lat_a, lon_b, lat_b])
    dlon, dlat = lon_b - lon_a, lat_b - lat_a
    a = sin(dlat / 2.0) ** 2 + cos(lat_a) * cos(lat_b) * sin(dlon / 2.0) ** 2
    a = max(0.0, min(1.0, a))
    return 2 * asin(sqrt(a)) * EARTH_RADIUS_KM


class HtraeNCS:
    @staticmethod
    async def get_server_scores(
        regions: List[BotRegions],
        users: List[MMBotUsers],
        servers: List[RconServers]
    ) -> List[Tuple[RconServers, float]]:
        if not users or not servers:
            return []

        scored_servers = []
        for server in servers:
            s_coords = await HtraeNCS._get_coords(regions, server)

            user_scores = []
            for user in users:
                u_coords = await HtraeNCS._get_coords(regions, user)
                same_region = bool(user.region and user.region == server.region)
                rtt = HtraeNCS._predict_rtt(u_coords, s_coords, same_region)
                user_scores.append(HtraeNCS._rtt_to_score(rtt))

            avg_score = sum(user_scores) / len(user_scores) if user_scores else -1.0
            scored_servers.append((server, avg_score))

        return sorted(scored_servers, key=lambda x: x[1], reverse=True)

    @staticmethod
    async def _get_coords(
        regions: List[BotRegions],
        target: MMBotUsers | RconServers
    ) -> Tuple[float, float, float, float]:
        if target.lat is not None and target.lon is not None:
            return (
                cast(float, target.lat),
                cast(float, target.lon),
                cast(float, target.height) if target.height is not None else DEFAULT_HEIGHT_MS,
                cast(float, target.uncertainty) if target.uncertainty is not None else DEFAULT_UNCERTAINTY,
            )

        region = {r.label: r for r in regions}.get(target.region)
        if region and region.base_latitude is not None and region.base_longitude is not None:
            return (
                cast(float, region.base_latitude),
                cast(float, region.base_longitude),
                cast(float, region.base_height) if region.base_height is not None else DEFAULT_HEIGHT_MS,
                DEFAULT_UNCERTAINTY,
            )

        raise ValueError(
            f"No coordinates or region fallback for "
            f"{target.user_id if isinstance(target, MMBotUsers) else f'{target.host}:{target.port}'}"
        )

    @staticmethod
    def _predict_rtt(
        u_coords: tuple, s_coords: tuple, same_region: bool = False
    ) -> float:
        u_lat, u_lon, u_height, _ = u_coords
        s_lat, s_lon, s_height, _ = s_coords

        distance_km = haversine(u_lat, u_lon, s_lat, s_lon)
        combined_height = u_height + s_height

        if same_region and distance_km < AS_CORRECTION_THRESHOLD_KM:
            combined_height *= AS_HEIGHT_REDUCTION

        return distance_km * MS_PER_KM + combined_height

    @staticmethod
    def _rtt_to_score(rtt: float) -> float:
        if rtt <= 50:
            return 1.0
        elif rtt >= 150:
            return -1.0
        return 0.5 - (rtt - 50) / 100.0

    @staticmethod
    async def update_coordinates(
        bot: "Bot",
        regions: List[BotRegions],
        server: RconServers,
        user_rtts: List[Tuple[MMBotUsers, float]],
    ) -> None:
        s_coords = await HtraeNCS._get_coords(regions, server)
        user_updates: Dict[int, Tuple[float, float, float, float]] = {}
        server_deltas = []

        for user, measured_rtt in user_rtts:
            if measured_rtt <= 0:
                continue

            u_coords = await HtraeNCS._get_coords(regions, user)
            same_region = user.region == server.region
            predicted_rtt = HtraeNCS._predict_rtt(u_coords, s_coords, same_region)
            error = measured_rtt - predicted_rtt

            # TIV check: anomalous measurement when both nodes are confident
            # but prediction is wildly off. Increase uncertainty instead of
            # moving coordinates based on a bad sample.
            if (
                abs(error) > TIV_THRESHOLD_MS
                and u_coords[3] < 0.1
                and s_coords[3] < 0.1
            ):
                new_unc = min(MAX_UNCERTAINTY, u_coords[3] * 1.1)
                user_updates[cast(int, user.user_id)] = (
                    u_coords[0], u_coords[1], u_coords[2], new_unc
                )
                continue

            u_new = HtraeNCS._adjust_position(
                u_coords, s_coords, measured_rtt, error, is_server=False
            )
            user_updates[cast(int, user.user_id)] = u_new

            s_new = HtraeNCS._adjust_position(
                s_coords, u_coords, measured_rtt, error, is_server=True
            )
            server_deltas.append(tuple(a - b for a, b in zip(s_new, s_coords)))

        if not user_updates:
            return

        await bot.store.update_user_coords(
            guild_id=user_rtts[0][0].guild_id, user_coords=user_updates
        )

        if server_deltas:
            avg_delta = tuple(
                sum(d) / len(server_deltas) for d in zip(*server_deltas)
            )
            await bot.store.update(
                RconServers,
                id=server.id,
                lat=max(-90.0, min(90.0, s_coords[0] + avg_delta[0])),
                lon=max(-180.0, min(180.0, s_coords[1] + avg_delta[1])),
                height=max(MIN_HEIGHT_MS, min(MAX_HEIGHT_MS, s_coords[2] + avg_delta[2])),
                uncertainty=max(MIN_UNCERTAINTY, min(MAX_UNCERTAINTY, s_coords[3] + avg_delta[3])),
            )

    @staticmethod
    def _adjust_position(
        source: tuple,
        target: tuple,
        measured_rtt: float,
        error: float,
        is_server: bool = False,
    ) -> Tuple[float, float, float, float]:
        """Vivaldi-inspired coordinate adjustment.

        Moves source relative to target based on RTT prediction error.
        Positive error (measured > predicted) -> move AWAY  (distance underestimated)
        Negative error (measured < predicted) -> move TOWARD (distance overestimated)
        """
        s_lat, s_lon, s_height, s_unc = source
        t_lat, t_lon, _, t_unc = target

        # Weight: higher LOCAL uncertainty -> move more (less confident in own position)
        weight = s_unc / (s_unc + t_unc) if (s_unc + t_unc) > 0 else 0.5

        # Step size
        delta = CC * weight
        if is_server:
            delta *= SERVER_MOVE_FACTOR

        # --- Geographic direction (source AWAY from target) in km-space ---
        avg_lat_rad = radians((s_lat + t_lat) / 2.0)
        cos_avg_lat = max(cos(avg_lat_rad), 0.01)  # guard near poles
        km_per_deg_lon = KM_PER_DEG_LAT * cos_avg_lat

        dlat_km = (s_lat - t_lat) * KM_PER_DEG_LAT
        dlon_km = (s_lon - t_lon) * km_per_deg_lon
        flat_dist_km = sqrt(dlat_km ** 2 + dlon_km ** 2)

        if flat_dist_km > 0.01:
            unit_dlat = dlat_km / flat_dist_km
            unit_dlon = dlon_km / flat_dist_km

            # Movement in km, capped to prevent large jumps
            move_km = delta * error / MS_PER_KM
            move_km = max(-MAX_MOVE_KM, min(MAX_MOVE_KM, move_km))

            new_lat = s_lat + (unit_dlat * move_km) / KM_PER_DEG_LAT
            new_lon = s_lon + (unit_dlon * move_km) / km_per_deg_lon
        else:
            # Co-located: small deterministic perturbation to break symmetry
            nudge = 0.01 if error > 0 else -0.01
            new_lat = s_lat + nudge
            new_lon = s_lon + nudge

        # --- Height update ---
        # Height absorbs local network overhead not explained by distance.
        # Positive error (measured > predicted) -> increase height (more local delay)
        # Negative error (measured < predicted) -> decrease height (less local delay)
        new_height = s_height + delta * error * 0.25
        new_height = max(MIN_HEIGHT_MS, min(MAX_HEIGHT_MS, new_height))

        # --- Uncertainty update (adaptive, bidirectional) ---
        # Exponential moving average of relative prediction error.
        # Good predictions -> uncertainty drops. Bad predictions -> uncertainty rises.
        sample_error = abs(error) / max(1.0, measured_rtt)
        new_unc = sample_error * CE * weight + s_unc * (1 - CE * weight)
        new_unc = max(MIN_UNCERTAINTY, min(MAX_UNCERTAINTY, new_unc))

        # --- Clamp to valid geographic range ---
        new_lat = max(-90.0, min(90.0, new_lat))
        new_lon = max(-180.0, min(180.0, new_lon))

        return (new_lat, new_lon, new_height, new_unc)


get_server_scores = HtraeNCS.get_server_scores
update_coordinates = HtraeNCS.update_coordinates
