"""
事件去重器
用于防止同一地震事件被多个数据源重复推送
只推送最先获取到的数据源
"""

from datetime import datetime, timedelta
from typing import Any

from astrbot.api import logger

from .models import DataSource, DisasterEvent, EarthquakeData


class EventDeduplicator:
    """简单事件去重器 - 只推送最先获取到的数据源"""

    def __init__(
        self,
        time_window_minutes: int = 1,
        location_tolerance_km: float = 20.0,
        magnitude_tolerance: float = 0.5,
    ):
        """
        初始化去重器

        Args:
            time_window_minutes: 时间窗口（分钟），默认1分钟
            location_tolerance_km: 位置容差（公里），默认20公里
            magnitude_tolerance: 震级容差，默认0.5级
        """
        self.time_window = timedelta(minutes=time_window_minutes)
        self.location_tolerance = location_tolerance_km
        self.magnitude_tolerance = magnitude_tolerance

        # 记录最近的事件：事件指纹 -> 首次接收信息
        self.recent_events: dict[str, dict] = {}

    def should_push_event(self, event: DisasterEvent) -> bool:
        """判断是否应该推送事件 - 只推送首次接收的"""
        if not isinstance(event.data, EarthquakeData):
            logger.debug(
                f"[灾害预警] 非地震事件，直接允许推送: {event.disaster_type.value}"
            )
            return True  # 非地震事件直接推送

        earthquake = event.data

        # 生成事件指纹
        event_fingerprint = self._generate_event_fingerprint(earthquake)

        # 关键修复：如果地震时间解析失败，使用当前时间作为后备
        # 但要去重逻辑仍然有效
        current_time = earthquake.shock_time if earthquake.shock_time is not None else datetime.now()

        logger.debug(
            f"[灾害预警] 检查事件去重: {event.source.value}, 震级: {earthquake.magnitude}, 位置: {earthquake.place_name}"
        )
        logger.debug(f"[灾害预警] 事件指纹: {event_fingerprint}")
        logger.debug(
            f"[灾害预警] 当前时间: {current_time}, 时间窗口: {self.time_window}"
        )

        # 检查是否已有相似事件
        if event_fingerprint in self.recent_events:
            existing_event = self.recent_events[event_fingerprint]

            # 如果在时间窗口内，说明是重复事件
            time_diff = abs(
                (current_time - existing_event["timestamp"]).total_seconds() / 60
            )
            logger.debug(
                f"[灾害预警] 发现相似事件，时间差: {time_diff}分钟, 时间窗口: {self.time_window.total_seconds() / 60}分钟"
            )

            if time_diff <= self.time_window.total_seconds() / 60:
                # 检查是否允许状态升级或报数更新
                if self._should_allow_update(earthquake, existing_event):
                    logger.info(
                        f"[灾害预警] 状态升级/报数更新: {event.source.value} -> {existing_event['source']}"
                    )
                    # 更新记录但允许推送
                    self.recent_events[event_fingerprint] = {
                        "timestamp": current_time,
                        "source": event.source.value,
                        "latitude": earthquake.latitude or 0,
                        "longitude": earthquake.longitude or 0,
                        "magnitude": earthquake.magnitude or 0,
                        "info_type": earthquake.info_type or "",
                        "updates": getattr(earthquake, "updates", 1),
                        "is_final": getattr(earthquake, "is_final", False),
                    }
                    return True
                else:
                    logger.info(
                        f"[灾害预警] 跳过重复事件: {event.source.value} - {existing_event['source']} 已推送相似事件"
                    )
                    return False
            else:
                logger.debug("[灾害预警] 相似事件已过期，允许推送")

        # 新事件或过期事件，记录并允许推送
        self.recent_events[event_fingerprint] = {
            "timestamp": current_time,
            "source": event.source.value,
            "latitude": earthquake.latitude or 0,
            "longitude": earthquake.longitude or 0,
            "magnitude": earthquake.magnitude or 0,
            "info_type": earthquake.info_type or "",
            "updates": getattr(earthquake, "updates", 1),
            "is_final": getattr(earthquake, "is_final", False),
        }

        logger.info(f"[灾害预警] 允许推送新事件: {event.source.value}")
        return True

    def _generate_event_fingerprint(self, earthquake: EarthquakeData) -> str:
        """生成事件指纹 - 基于地理位置和震级的简化指纹"""
        if not earthquake.latitude or not earthquake.longitude:
            return "unknown_location"

        # 将坐标量化到指定精度（20km网格）
        lat_grid = round(earthquake.latitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )
        lon_grid = round(earthquake.longitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )

        # 震级量化到容差级别
        mag_grid = (
            round((earthquake.magnitude or 0) / self.magnitude_tolerance)
            * self.magnitude_tolerance
        )

        # 关键修复：处理时间可能为None的情况
        if earthquake.shock_time is not None:
            time_minute = earthquake.shock_time.replace(second=0, microsecond=0)
        else:
            # 如果时间解析失败，使用当前时间但标记为特殊值
            # 这样同一批无时间的事件仍然可以被正确去重
            time_minute = datetime.now().replace(second=0, microsecond=0)

        return f"{lat_grid:.3f},{lon_grid:.3f},{mag_grid:.1f},{time_minute.strftime('%Y%m%d%H%M')}"

    def cleanup_old_events(self):
        """清理过期事件"""
        cutoff_time = datetime.now() - self.time_window * 2  # 保留2倍时间窗口

        old_fingerprints = []
        for fingerprint, event_info in self.recent_events.items():
            if event_info["timestamp"] < cutoff_time:
                old_fingerprints.append(fingerprint)

        for fingerprint in old_fingerprints:
            del self.recent_events[fingerprint]

    def get_deduplication_stats(self) -> dict[str, Any]:
        """获取去重统计"""
        return {
            "recent_events_count": len(self.recent_events),
            "time_window_minutes": self.time_window.total_seconds() / 60,
            "location_tolerance_km": self.location_tolerance,
            "magnitude_tolerance": self.magnitude_tolerance,
        }

    def _should_allow_update(
        self, current_earthquake: EarthquakeData, existing_event: dict
    ) -> bool:
        """判断是否应该允许事件更新 - 核心增强逻辑"""

        # ✅ 修复1: USGS automatic -> reviewed 状态升级
        if current_earthquake.source == DataSource.FAN_STUDIO_USGS:
            current_info_type = (current_earthquake.info_type or "").lower()
            existing_info_type = (existing_event.get("info_type", "") or "").lower()

            # automatic -> reviewed 升级应该允许
            if existing_info_type == "automatic" and current_info_type == "reviewed":
                logger.debug("[灾害预警] 允许USGS状态升级: automatic -> reviewed")
                return True

            # reviewed -> automatic 不应该发生，但如果发生也允许（可能是数据修正）
            if existing_info_type == "reviewed" and current_info_type == "automatic":
                logger.warning(
                    "[灾害预警] 检测到USGS状态降级: reviewed -> automatic，但仍允许推送"
                )
                return True

        # ✅ 修复2: 报数更新检查
        current_updates = getattr(current_earthquake, "updates", 1)
        existing_updates = existing_event.get("updates", 1)

        if current_updates > existing_updates:
            logger.info(
                f"[灾害预警] 报数更新: 第{existing_updates}报 -> 第{current_updates}报"
            )
            return True

        # ✅ 修复3: 最终报检查
        if getattr(current_earthquake, "is_final", False) and not existing_event.get(
            "is_final", False
        ):
            logger.info("[灾害预警] 去重允许最终报推送: 非最终报 -> 最终报")
            return True

        # ✅ 修复4: 同一数据源的状态升级
        if current_earthquake.source.value == existing_event["source"]:
            # 同一数据源的更新应该允许
            if current_updates > existing_updates:
                logger.info(
                    f"[灾害预警] 允许同一数据源报数更新: {current_earthquake.source.value}"
                )
                return True

        return False

    def record_event(self, event: DisasterEvent):
        """记录事件（用于消息管理器调用）"""
        # 这个方法是为了兼容消息管理器的调用
        # 这里不需要额外操作，实际的去重逻辑已经在 should_push_event 中处理
        if event and isinstance(event.data, EarthquakeData):
            # 可以在这里添加额外的记录逻辑，如果需要的话
            pass
