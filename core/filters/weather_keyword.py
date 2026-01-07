"""
气象预警关键词过滤器
支持按关键词白名单过滤气象预警（支持省份、城市、区县、预警类型等任意关键词）
"""

from typing import Any

from astrbot.api import logger


class WeatherKeywordFilter:
    """气象预警关键词过滤器"""

    def __init__(self, config: dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.keywords = config.get("keywords", [])

        if self.enabled and self.keywords:
            logger.info(
                f"[灾害预警] 气象预警关键词过滤器已启用，关键词白名单: {', '.join(self.keywords)}"
            )
        elif self.enabled:
            logger.info(
                "[灾害预警] 气象预警关键词过滤器已启用，但关键词列表为空，将推送全国预警"
            )

    def should_filter(self, headline: str) -> bool:
        """
        判断是否应过滤该预警
        返回 True 表示应过滤（不推送），False 表示不过滤（推送）
        """
        # 未启用过滤或关键词列表为空，不过滤任何预警
        if not self.enabled or not self.keywords:
            return False

        # 检查预警标题中是否包含任意一个关键词
        if not headline:
            return False

        headline_lower = headline.lower()
        for keyword in self.keywords:
            if keyword.lower() in headline_lower:
                return False  # 匹配到关键词，不过滤（推送）

        # 未匹配到关键词，过滤（不推送）
        logger.info(
            f"[灾害预警] 气象预警被关键词过滤器过滤: 标题中未包含任何关键词（标题: {headline[:50]}...）"
        )
        return True
