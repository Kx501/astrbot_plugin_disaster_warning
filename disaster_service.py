"""
核心灾害预警服务
"""

import asyncio
import json
import traceback
from datetime import datetime
from typing import Any

from astrbot.api import logger

from .data_handlers import (
    FanStudioHandler,
    GlobalQuakeHandler,
    P2PDataHandler,
    WolfxDataHandler,
)
from .message_logger import MessageLogger
from .message_manager import MessagePushManager
from .models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from .websocket_manager import GlobalQuakeClient, HTTPDataFetcher, WebSocketManager


class DisasterWarningService:
    """灾害预警核心服务"""

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context
        self.running = False

        # 初始化消息记录器
        self.message_logger = MessageLogger(config, "disaster_warning")

        # 初始化组件
        self.ws_manager = WebSocketManager(
            config.get("websocket_config", {}), self.message_logger
        )
        self.http_fetcher: HTTPDataFetcher | None = None
        self.message_manager = MessagePushManager(config, context)

        # 数据处理器
        self.handlers = {
            "fan_studio": FanStudioHandler(self.message_logger),
            "p2p": P2PDataHandler(self.message_logger),
            "wolfx": WolfxDataHandler(self.message_logger),
            "global_quake": GlobalQuakeHandler(self.message_logger),
        }

        # 连接配置
        self.connections = {}
        self.connection_tasks = []

        # 定时任务
        self.scheduled_tasks = []

    async def initialize(self):
        """初始化服务"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警服务...")

            # 初始化HTTP获取器
            self.http_fetcher = HTTPDataFetcher(self.config)

            # 注册WebSocket消息处理器
            self._register_handlers()

            # 配置连接
            self._configure_connections()

            logger.info("[灾害预警] 灾害预警服务初始化完成")

        except Exception as e:
            logger.error(f"[灾害预警] 初始化服务失败: {e}")
            raise

    def _register_handlers(self):
        """注册消息处理器"""

        # FAN Studio WebSocket处理器 - 修复source信息传递
        async def fan_studio_handler(message, connection_name=None):
            handler = self.handlers["fan_studio"]
            # 关键修复：通过连接名称推断具体的数据源
            if connection_name:
                # 根据连接名称映射到具体的数据源
                source_map = {
                    "fan_studio_cenc": DataSource.FAN_STUDIO_CENC,
                    "fan_studio_cwa": DataSource.FAN_STUDIO_CWA,
                    "fan_studio_cea": DataSource.FAN_STUDIO_CEA,
                    "fan_studio_usgs": DataSource.FAN_STUDIO_USGS,
                    "fan_studio_weather": DataSource.FAN_STUDIO_WEATHER,
                    "fan_studio_tsunami": DataSource.FAN_STUDIO_TSUNAMI,
                }

                # 获取目标数据源
                target_source = source_map.get(connection_name)
                if target_source:
                    # 临时修改处理器的source，确保正确识别
                    original_source = handler.source
                    handler.source = target_source
                    event = handler.parse_message(
                        message, connection_name=connection_name
                    )
                    handler.source = original_source  # 恢复原始source
                else:
                    logger.warning(
                        f"[灾害预警] FAN Studio处理器无法识别连接名称: {connection_name}"
                    )
                    event = handler.parse_message(
                        message, connection_name=connection_name
                    )
            else:
                logger.warning(
                    "[灾害预警] FAN Studio处理器未收到连接名称，使用默认处理"
                )
                event = handler.parse_message(message)

            if event:
                logger.debug(f"[灾害预警] FAN Studio处理器解析成功: {event.id}")
                await self._handle_disaster_event(event)
            else:
                logger.debug("[灾害预警] FAN Studio处理器返回None，无有效事件")

        self.ws_manager.register_handler("fan_studio", fan_studio_handler)

        # P2P WebSocket处理器 - 修复source信息传递
        async def p2p_handler(message, connection_name=None):
            logger.debug(f"[灾害预警] P2P处理器收到消息，长度: {len(message)}")
            handler = self.handlers["p2p"]
            # P2P连接名称映射
            if connection_name:
                source_map = {
                    "p2p_main": DataSource.P2P_EARTHQUAKE,
                    "p2p_eew": DataSource.P2P_EEW,
                }
                original_source = handler.source
                handler.source = source_map.get(connection_name, handler.source)
                event = handler.parse_message(message)
                handler.source = original_source
            else:
                event = handler.parse_message(message)

            if event:
                logger.debug(f"[灾害预警] P2P处理器解析成功: {event.id}")
                await self._handle_disaster_event(event)
            else:
                logger.debug("[灾害预警] P2P处理器返回None，无有效事件")

        self.ws_manager.register_handler("p2p", p2p_handler)

        # Wolfx WebSocket处理器 - 修复source信息传递
        async def wolfx_handler(message, connection_name=None):
            handler = self.handlers["wolfx"]
            # Wolfx连接名称映射
            if connection_name:
                source_map = {
                    "wolfx_japan_jma_eew": DataSource.WOLFX_JMA_EEW,
                    "wolfx_china_cenc_eew": DataSource.WOLFX_CENC_EEW,
                    "wolfx_taiwan_cwa_eew": DataSource.WOLFX_CWA_EEW,
                    "wolfx_china_cenc_earthquake": DataSource.WOLFX_CENC_EEW,
                    "wolfx_japan_jma_earthquake": DataSource.WOLFX_JMA_EEW,
                }
                original_source = handler.source
                handler.source = source_map.get(connection_name, handler.source)
                event = handler.parse_message(message)
                handler.source = original_source
            else:
                event = handler.parse_message(message)

            if event:
                logger.debug(f"[灾害预警] Wolfx处理器解析成功: {event.id}")
                await self._handle_disaster_event(event)

        self.ws_manager.register_handler("wolfx", wolfx_handler)

    def _configure_connections(self):
        """配置连接 - 适配新的细粒度数据源配置"""
        data_sources = self.config.get("data_sources", {})

        # FAN Studio连接配置
        fan_studio_config = data_sources.get("fan_studio", {})
        if isinstance(fan_studio_config, dict) and fan_studio_config.get(
            "enabled", True
        ):
            # 中国地震网地震预警
            if fan_studio_config.get("china_earthquake_warning", True):
                self.connections["fan_studio_cea"] = {
                    "url": "wss://ws.fanstudio.tech/cea",
                    "handler": "fan_studio",
                }

            # 台湾中央气象署强震即时警报
            if fan_studio_config.get("taiwan_cwa_earthquake", True):
                self.connections["fan_studio_cwa"] = {
                    "url": "wss://ws.fanstudio.tech/cwa",
                    "handler": "fan_studio",
                }

            # 中国地震台网地震测定
            if fan_studio_config.get("china_cenc_earthquake", True):
                self.connections["fan_studio_cenc"] = {
                    "url": "wss://ws.fanstudio.tech/cenc",
                    "handler": "fan_studio",
                }

            # USGS地震测定
            if fan_studio_config.get("usgs_earthquake", True):
                self.connections["fan_studio_usgs"] = {
                    "url": "wss://ws.fanstudio.tech/usgs",
                    "handler": "fan_studio",
                }

            # 中国气象局气象预警
            if fan_studio_config.get("china_weather_alarm", True):
                self.connections["fan_studio_weather"] = {
                    "url": "wss://ws.fanstudio.tech/weatheralarm",
                    "handler": "fan_studio",
                }

            # 自然资源部海啸预警
            if fan_studio_config.get("china_tsunami", True):
                self.connections["fan_studio_tsunami"] = {
                    "url": "wss://ws.fanstudio.tech/tsunami",
                    "handler": "fan_studio",
                }

        # P2P连接配置
        p2p_config = data_sources.get("p2p_earthquake", {})
        if isinstance(p2p_config, dict) and p2p_config.get("enabled", True):
            # 检查是否有任何P2P数据源被启用
            p2p_enabled = False
            if p2p_config.get("japan_jma_eew", True):
                p2p_enabled = True
            if p2p_config.get("japan_jma_earthquake", True):
                p2p_enabled = True
            if p2p_config.get("japan_jma_tsunami", True):
                p2p_enabled = True

            if p2p_enabled:
                self.connections["p2p_main"] = {
                    "url": "wss://api.p2pquake.net/v2/ws",
                    "handler": "p2p",
                }

        # Wolfx连接配置
        wolfx_config = data_sources.get("wolfx", {})
        if isinstance(wolfx_config, dict) and wolfx_config.get("enabled", True):
            wolfx_sources = [
                ("japan_jma_eew", "wss://ws-api.wolfx.jp/jma_eew"),
                ("china_cenc_eew", "wss://ws-api.wolfx.jp/cenc_eew"),
                ("taiwan_cwa_eew", "wss://ws-api.wolfx.jp/cwa_eew"),
                ("japan_jma_earthquake", "wss://ws-api.wolfx.jp/jma_eqlist"),
                ("china_cenc_earthquake", "wss://ws-api.wolfx.jp/cenc_eqlist"),
            ]

            for source_key, url in wolfx_sources:
                if wolfx_config.get(source_key, True):
                    conn_name = f"wolfx_{source_key}"
                    self.connections[conn_name] = {"url": url, "handler": "wolfx"}

    async def start(self):
        """启动服务"""
        if self.running:
            return

        try:
            self.running = True
            logger.info("[灾害预警] 正在启动灾害预警服务...")

            # 启动WebSocket管理器
            await self.ws_manager.start()

            # 建立WebSocket连接
            await self._establish_websocket_connections()

            # 启动Global Quake连接（如果启用）
            global_quake_config = self.config.get("data_sources", {}).get(
                "global_quake", {}
            )
            logger.debug(f"[灾害预警] Global Quake配置检查: {global_quake_config}")
            if isinstance(global_quake_config, dict) and global_quake_config.get(
                "enabled", True
            ):
                # 检查是否有配置服务器地址 - 修复布尔值配置问题
                primary_server = global_quake_config.get(
                    "primary_server", "server-backup.globalquake.net"
                )
                secondary_server = global_quake_config.get(
                    "secondary_server", "server-backup.globalquake.net"
                )

                # 关键修复：确保服务器地址是字符串，而不是布尔值
                if isinstance(primary_server, bool):
                    primary_server = (
                        "server-backup.globalquake.net" if primary_server else ""
                    )
                if isinstance(secondary_server, bool):
                    secondary_server = (
                        "server-backup.globalquake.net" if secondary_server else ""
                    )

                primary_port = global_quake_config.get("primary_port", 38000)
                secondary_port = global_quake_config.get("secondary_port", 38000)
                logger.debug(
                    f"[灾害预警] Global Quake服务器配置 - 主: {primary_server}:{primary_port}, 备: {secondary_server}:{secondary_port}"
                )

                # 关键修复：确保服务器地址是有效的字符串，而不是布尔值
                if isinstance(primary_server, str) and primary_server.strip():
                    logger.debug(
                        "[灾害预警] Global Quake主服务器配置有效，准备启动连接"
                    )
                    await self._start_global_quake_connection()
                elif isinstance(secondary_server, str) and secondary_server.strip():
                    logger.debug(
                        "[灾害预警] Global Quake备服务器配置有效，准备启动连接"
                    )
                    await self._start_global_quake_connection()
                else:
                    logger.warning(
                        "[灾害预警] Global Quake未配置有效的服务器地址，跳过连接"
                    )
            else:
                logger.info("[灾害预警] Global Quake未启用或配置无效，跳过连接")

            # 启动定时HTTP数据获取
            await self._start_scheduled_http_fetch()

            # 启动清理任务
            await self._start_cleanup_task()

            logger.info("[灾害预警] 灾害预警服务已启动")

        except Exception as e:
            logger.error(f"[灾害预警] 启动服务失败: {e}")
            self.running = False
            raise

    async def stop(self):
        """停止服务"""
        if not self.running:
            return

        try:
            self.running = False
            logger.info("[灾害预警] 正在停止灾害预警服务...")

            # 取消所有任务
            for task in self.connection_tasks:
                task.cancel()

            for task in self.scheduled_tasks:
                task.cancel()

            # 停止WebSocket管理器
            await self.ws_manager.stop()

            # 关闭HTTP获取器
            if self.http_fetcher:
                await self.http_fetcher.__aexit__(None, None, None)

            logger.info("[灾害预警] 灾害预警服务已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 停止服务时出错: {e}")

    async def _establish_websocket_connections(self):
        """建立WebSocket连接"""
        for conn_name, conn_config in self.connections.items():
            if conn_config["handler"] in ["fan_studio", "p2p", "wolfx"]:
                task = asyncio.create_task(
                    self.ws_manager.connect(conn_name, conn_config["url"])
                )
                self.connection_tasks.append(task)
                logger.info(f"[灾害预警] 已启动WebSocket连接任务: {conn_name}")

    async def _start_global_quake_connection(self):
        """启动Global Quake连接"""
        try:
            global_quake_config = self.config.get("data_sources", {}).get(
                "global_quake", {}
            )
            logger.info(
                f"[灾害预警] 创建Global Quake客户端 - 配置: {global_quake_config}, 消息记录器: {self.message_logger is not None}"
            )
            global_quake_client = GlobalQuakeClient(
                global_quake_config, self.message_logger
            )

            # 注册消息处理器
            async def global_quake_handler(message):
                handler = self.handlers["global_quake"]
                event = handler.parse_message(message)
                if event:
                    await self._handle_disaster_event(event)

            global_quake_client.register_handler(global_quake_handler)

            # 连接并监听
            if await global_quake_client.connect():
                task = asyncio.create_task(global_quake_client.listen())
                self.connection_tasks.append(task)
                logger.info(
                    f"[灾害预警] Global Quake连接已启动 (当前活跃的后台连接任务数量: {len(self.connection_tasks)})"
                )
            else:
                logger.error("[灾害预警] Global Quake连接失败")

        except Exception as e:
            logger.error(f"[灾害预警] 启动Global Quake连接失败: {e}")

    async def _start_scheduled_http_fetch(self):
        """启动定时HTTP数据获取"""

        # 定时获取Wolfx的地震列表数据
        async def fetch_wolfx_data():
            while self.running:
                try:
                    await asyncio.sleep(300)  # 5分钟获取一次

                    async with self.http_fetcher as fetcher:
                        # 获取中国地震台网列表
                        cenc_data = await fetcher.fetch_json(
                            "https://api.wolfx.jp/cenc_eqlist.json"
                        )
                        if cenc_data:
                            # 记录HTTP响应
                            if self.message_logger:
                                self.message_logger.log_http_response(
                                    "https://api.wolfx.jp/cenc_eqlist.json",
                                    cenc_data,
                                    200,
                                )

                            handler = self.handlers["wolfx"]
                            event = handler.parse_message(json.dumps(cenc_data))
                            if event:
                                await self._handle_disaster_event(event)

                        # 获取日本气象厅地震列表
                        jma_data = await fetcher.fetch_json(
                            "https://api.wolfx.jp/jma_eqlist.json"
                        )
                        if jma_data:
                            # 记录HTTP响应
                            if self.message_logger:
                                self.message_logger.log_http_response(
                                    "https://api.wolfx.jp/jma_eqlist.json",
                                    jma_data,
                                    200,
                                )

                            handler = self.handlers["wolfx"]
                            event = handler.parse_message(json.dumps(jma_data))
                            if event:
                                await self._handle_disaster_event(event)

                except Exception as e:
                    logger.error(f"[灾害预警] 定时HTTP数据获取失败: {e}")

        task = asyncio.create_task(fetch_wolfx_data())
        self.scheduled_tasks.append(task)

    async def _start_cleanup_task(self):
        """启动清理任务"""

        async def cleanup():
            while self.running:
                try:
                    await asyncio.sleep(86400)  # 每天清理一次
                    self.message_manager.cleanup_old_records()
                except Exception as e:
                    logger.error(f"[灾害预警] 清理任务失败: {e}")

        task = asyncio.create_task(cleanup())
        self.scheduled_tasks.append(task)

    async def _handle_disaster_event(self, event: DisasterEvent):
        """处理灾害事件"""
        try:
            logger.debug(f"[灾害预警] 处理灾害事件: {event.id}")
            self._log_event(event)

            # 推送消息
            push_result = await self.message_manager.push_event(event)
            if push_result:
                logger.debug(f"[灾害预警] ✅ 事件推送成功: {event.id}")
            else:
                logger.debug(f"[灾害预警] 事件推送被过滤: {event.id}")

        except Exception as e:
            logger.error(f"[灾害预警] 处理灾害事件失败: {e}")
            logger.error(
                f"[灾害预警] 失败的事件ID: {event.id if hasattr(event, 'id') else 'unknown'}"
            )
            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

    def _log_event(self, event: DisasterEvent):
        """记录事件日志 - 使用专门格式化器提供完整信息"""
        # 使用专门格式化器提供完整的事件信息
        try:
            if isinstance(event.data, EarthquakeData):
                # 地震事件：显示关键信息
                earthquake = event.data
                log_info = f"地震事件 - 震级: M{earthquake.magnitude}, 位置: {earthquake.place_name}, 时间: {earthquake.shock_time}, 数据源: {event.source.value}"
            elif isinstance(event.data, TsunamiData):
                # 海啸事件：显示关键信息
                tsunami = event.data
                log_info = f"海啸事件 - 级别: {tsunami.level}, 标题: {tsunami.title}, 数据源: {event.source.value}"
            elif isinstance(event.data, WeatherAlarmData):
                # 气象事件：显示关键信息
                weather = event.data
                log_info = (
                    f"气象事件 - 标题: {weather.headline}, 数据源: {event.source.value}"
                )
            else:
                # 未知事件类型
                log_info = (
                    f"未知事件类型 - ID: {event.id}, 数据源: {event.source.value}"
                )

            logger.debug(f"[灾害预警] 事件详情: {log_info}")
        except Exception:
            # 如果专门格式化失败，使用基础信息
            logger.debug(
                f"[灾害预警] 事件详情: ID={event.id}, 类型={event.disaster_type.value}, 数据源={event.source.value}"
            )

    def get_service_status(self) -> dict[str, Any]:
        """获取服务状态"""
        return {
            "running": self.running,
            "active_connections": len(self.ws_manager.connections),
            "push_stats": self.message_manager.get_push_stats(),
            "data_sources": self._get_active_data_sources(),
        }

    def _get_active_data_sources(self) -> list[str]:
        """获取活跃的数据源 - 适配新的细粒度配置结构"""
        active_sources = []
        data_sources = self.config.get("data_sources", {})

        # 遍历新的配置结构，收集启用的数据源
        for service_name, service_config in data_sources.items():
            if isinstance(service_config, dict) and service_config.get(
                "enabled", False
            ):
                # 收集该服务下启用的具体数据源
                for source_name, enabled in service_config.items():
                    if (
                        source_name != "enabled"
                        and isinstance(enabled, bool)
                        and enabled
                    ):
                        active_sources.append(f"{service_name}.{source_name}")

        return active_sources

    async def test_push(self, session: str, disaster_type: str = "earthquake"):
        """测试推送功能 - 支持多种灾害类型"""
        try:
            # 根据灾害类型创建不同的测试事件
            if disaster_type == "earthquake":
                # 地震测试事件
                test_data = EarthquakeData(
                    id="test_earthquake_123",
                    event_id="test_event_123",
                    source=DataSource.FAN_STUDIO_CENC,
                    disaster_type=DisasterType.EARTHQUAKE,
                    shock_time=datetime.now(),
                    latitude=35.0,
                    longitude=105.0,
                    magnitude=5.5,
                    depth=10.0,
                    intensity=6.0,
                    place_name="测试地震地点",
                    raw_data={},
                )
                disaster_type_enum = DisasterType.EARTHQUAKE

            elif disaster_type == "tsunami":
                # 海啸测试事件
                test_data = TsunamiData(
                    id="test_tsunami_123",
                    code="test_tsunami_code",
                    source=DataSource.FAN_STUDIO_TSUNAMI,
                    title="海啸警报测试",
                    level="Warning",
                    org_unit="测试海啸预警中心",
                    forecasts=[
                        {"name": "测试海域", "grade": "Warning", "immediate": True}
                    ],
                    raw_data={},
                )
                disaster_type_enum = DisasterType.TSUNAMI

            elif disaster_type == "weather":
                # 气象预警测试事件
                test_data = WeatherAlarmData(
                    id="test_weather_123",
                    source=DataSource.FAN_STUDIO_WEATHER,
                    headline="大风蓝色预警信号测试",
                    title="大风蓝色预警信号",
                    description="测试气象台发布大风蓝色预警信号：预计今天白天全市沿岸海域和沿海地区将有西南风5～6级，阵风7～8级。",
                    type="wind",
                    effective_time=datetime.now(),
                    longitude=116.0,
                    latitude=39.0,
                    raw_data={},
                )
                disaster_type_enum = DisasterType.WEATHER_ALARM

            else:
                # 默认创建地震事件
                logger.warning(
                    f"[灾害预警] 未知的灾害类型 '{disaster_type}'，使用默认地震类型"
                )
                test_data = EarthquakeData(
                    id="test_earthquake_123",
                    event_id="test_event_123",
                    source=DataSource.FAN_STUDIO_CENC,
                    disaster_type=DisasterType.EARTHQUAKE,
                    shock_time=datetime.now(),
                    latitude=35.0,
                    longitude=105.0,
                    magnitude=5.5,
                    depth=10.0,
                    intensity=6.0,
                    place_name="测试地震地点",
                    raw_data={},
                )
                disaster_type_enum = DisasterType.EARTHQUAKE

            test_event = DisasterEvent(
                id=test_data.id,
                data=test_data,
                source=test_data.source,
                disaster_type=disaster_type_enum,
            )

            logger.info(f"[灾害预警] 创建{disaster_type}测试事件: {test_event.id}")

            # 直接推送（绕过频率控制）
            message = self.message_manager._build_message(test_event)
            await self.message_manager._send_message(session, message)

            logger.info(f"[灾害预警] {disaster_type}测试推送成功")
            return True

        except Exception as e:
            logger.error(f"[灾害预警] {disaster_type}测试推送失败: {e}")
            return False


# 服务实例
_disaster_service: DisasterWarningService | None = None


async def get_disaster_service(
    config: dict[str, Any], context
) -> DisasterWarningService:
    """获取灾害预警服务实例"""
    global _disaster_service

    if _disaster_service is None:
        _disaster_service = DisasterWarningService(config, context)
        await _disaster_service.initialize()

    return _disaster_service


async def stop_disaster_service():
    """停止灾害预警服务"""
    global _disaster_service

    if _disaster_service:
        await _disaster_service.stop()
        _disaster_service = None
