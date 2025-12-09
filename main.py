import asyncio
import os
import sys

# Windows平台WebSocket兼容性修复
# 解决websockets 12.0+ 在Windows上的ProactorEventLoop兼容性问题
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .disaster_service import get_disaster_service, stop_disaster_service


class DisasterWarningPlugin(Star):
    """多数据源灾害预警插件，支持地震、海啸、气象预警"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.disaster_service = None
        self._service_task = None

    async def initialize(self):
        """初始化插件"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警插件...")

            # 检查插件是否启用
            if not self.config.get("enabled", True):
                logger.info("[灾害预警] 插件已禁用，跳过初始化")
                return

            # 获取灾害预警服务
            self.disaster_service = await get_disaster_service(
                self.config, self.context
            )

            # 启动服务
            self._service_task = asyncio.create_task(self.disaster_service.start())

            logger.info("[灾害预警] 灾害预警插件初始化完成")

        except Exception as e:
            logger.error(f"[灾害预警] 插件初始化失败: {e}")
            raise

    async def terminate(self):
        """插件销毁时调用"""
        try:
            logger.info("[灾害预警] 正在停止灾害预警插件...")

            # 停止服务任务
            if self._service_task:
                self._service_task.cancel()
                try:
                    await self._service_task
                except asyncio.CancelledError:
                    pass

            # 停止灾害预警服务
            await stop_disaster_service()

            logger.info("[灾害预警] 灾害预警插件已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 插件停止时出错: {e}")

    @filter.command("灾害预警")
    async def disaster_warning_help(self, event: AstrMessageEvent):
        """灾害预警插件帮助"""
        help_text = """🚨 灾害预警插件使用说明

📋 可用命令：
• /灾害预警状态 - 查看服务运行状态
• /灾害预警测试 [群号] [灾害类型] - 测试推送功能
• /灾害预警统计 - 查看推送统计信息
• /灾害预警配置 查看 - 查看当前配置摘要
• /灾害预警去重统计 - 查看事件去重统计
• /灾害预警日志 - 查看原始消息日志统计
• /灾害预警日志开关 - 开关原始消息日志记录
• /灾害预警日志清除 - 清除所有原始消息日志
• /灾害预警帮助 - 显示此帮助信息

⚙️ 配置说明：
插件支持通过WebUI进行配置，包括：
• 数据源选择（地震、海啸、气象等）
• 推送阈值设置（震级、烈度等）
• 频率控制（报数控制）
• 目标群号设置
• 消息过滤（心跳包、P2P节点状态、重复事件等）

🔧 注意事项：
• 需要先在WebUI中配置目标QQ群号
• 插件会自动过滤低于阈值的灾害信息
• 支持多数据源实时推送
• 新增智能消息过滤功能，减少日志噪音"""

        yield event.plain_result(help_text)

    @filter.command("灾害预警状态")
    async def disaster_status(self, event: AstrMessageEvent):
        """查看灾害预警服务状态"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            status = self.disaster_service.get_service_status()

            status_text = f"""📊 灾害预警服务状态

🔄 运行状态：{"运行中" if status["running"] else "已停止"}
🔗 活跃连接：{status["active_connections"]} 个
📡 数据源：{len(status["data_sources"])} 个"""

            # 推送统计
            push_stats = status.get("push_stats", {})
            if push_stats:
                status_text += f"""
📈 推送统计：
  • 总事件数：{push_stats.get("total_events", 0)}
  • 总推送数：{push_stats.get("total_pushes", 0)}
  • 最终报数：{push_stats.get("final_reports_pushed", 0)}"""

            # 过滤统计（如果启用）
            if self.disaster_service and self.disaster_service.message_logger:
                filter_stats = self.disaster_service.message_logger.filter_stats
                if filter_stats and filter_stats["total_filtered"] > 0:
                    status_text += f"""
🎯 消息过滤统计：
  • 心跳包过滤：{filter_stats.get("heartbeat_filtered", 0)} 条
  • P2P节点状态过滤：{filter_stats.get("p2p_areas_filtered", 0)} 条
  • 重复事件过滤：{filter_stats.get("duplicate_events_filtered", 0)} 条
  • 连接状态过滤：{filter_stats.get("connection_status_filtered", 0)} 条
  • 总计过滤：{filter_stats.get("total_filtered", 0)} 条"""

            # 最近事件
            recent_events = push_stats.get("recent_events", [])
            if recent_events:
                status_text += f"""
🕐 最近24小时事件 (插件启动后)：{len(recent_events)} 个"""

            yield event.plain_result(status_text)

        except Exception as e:
            logger.error(f"[灾害预警] 获取服务状态失败: {e}")
            yield event.plain_result(f"❌ 获取服务状态失败: {str(e)}")

    @filter.command("灾害预警测试")
    async def disaster_test(
        self,
        event: AstrMessageEvent,
        target_group: str = None,
        disaster_type: str = None,
    ):
        """测试灾害预警推送功能 - 支持多种灾害类型"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            # 解析参数 - 支持多种参数组合
            target_session = None
            test_type = "earthquake"  # 默认测试地震

            # 参数解析逻辑
            if target_group and disaster_type:
                # 两个参数都提供：群号 + 灾害类型
                target_session = f"aiocqhttp:group:{target_group}"
                test_type = disaster_type

            elif target_group:
                # 只提供一个参数：需要判断是群号还是灾害类型
                if target_group in ["earthquake", "tsunami", "weather"]:
                    # 是灾害类型，使用当前群
                    target_session = event.unified_msg_origin
                    test_type = target_group
                else:
                    # 是群号，默认测试地震
                    target_session = f"aiocqhttp:group:{target_group}"
                    test_type = "earthquake"
            else:
                # 没有额外参数：使用当前群，默认测试地震
                target_session = event.unified_msg_origin
                test_type = "earthquake"

            # 验证灾害类型
            valid_types = ["earthquake", "tsunami", "weather"]
            if test_type not in valid_types:
                yield event.plain_result(
                    f"❌ 未知的灾害类型 '{test_type}'\n\n支持的类型：{', '.join(valid_types)}"
                )
                return

            # 执行测试
            logger.info(f"[灾害预警] 开始{test_type}测试推送到 {target_session}")
            success = await self.disaster_service.test_push(target_session, test_type)

            if success:
                # 获取灾害类型的中文名称
                type_names = {
                    "earthquake": "地震预警",
                    "tsunami": "海啸预警",
                    "weather": "气象预警",
                }
                type_name = type_names.get(test_type, test_type)
                yield event.plain_result(
                    f"✅ {type_name}测试推送已发送到 {target_session}"
                )
            else:
                yield event.plain_result("❌ 测试推送失败，请检查日志")

        except Exception as e:
            logger.error(f"[灾害预警] 测试推送失败: {e}")
            yield event.plain_result(f"❌ 测试推送失败: {str(e)}")

    @filter.command("灾害预警统计")
    async def disaster_stats(self, event: AstrMessageEvent):
        """查看推送统计信息"""
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 统计信息不可用")
            return

        try:
            stats = self.disaster_service.message_manager.get_push_stats()

            stats_text = f"""📈 灾害预警推送统计

📊 总体统计：
  • 总事件数：{stats["total_events"]}
  • 总推送数：{stats["total_pushes"]}
  • 最终报数：{stats["final_reports_pushed"]}

🕐 最近24小时 (插件启动后)：
  • 事件数：{len(stats["recent_events"])}"""

            # 显示最近的事件
            if stats["recent_events"]:
                stats_text += "\n\n📋 最近事件："
                for i, event in enumerate(stats["recent_events"][:5]):
                    stats_text += f"\n  {i + 1}. {event['event_id']} (推送{event['push_count']}次)"

            yield event.plain_result(stats_text)

        except Exception as e:
            logger.error(f"[灾害预警] 获取统计信息失败: {e}")
            yield event.plain_result(f"❌ 获取统计信息失败: {str(e)}")

    @filter.command_group("灾害预警配置")
    async def disaster_config(self, event: AstrMessageEvent):
        """灾害预警配置管理"""
        pass

    @disaster_config.command("查看")
    async def view_config(self, event: AstrMessageEvent):
        """查看当前配置"""
        try:
            config_summary = self._get_config_summary()
            yield event.plain_result(config_summary)
        except Exception as e:
            logger.error(f"[灾害预警] 获取配置摘要失败: {e}")
            yield event.plain_result("❌ 获取配置摘要失败")

    def _get_config_summary(self) -> str:
        """获取配置摘要"""
        summary = "⚙️ 灾害预警插件配置摘要\n\n"

        # 基本状态
        enabled = self.config.get("enabled", True)
        summary += f"🔧 插件状态：{'启用' if enabled else '禁用'}\n"

        # 目标群号
        target_groups = self.config.get("target_qq_groups", [])
        if target_groups:
            summary += f"📢 目标群号：{len(target_groups)} 个\n"
            for group in target_groups[:5]:
                summary += f"  • {group}\n"
            if len(target_groups) > 5:
                summary += f"  ...等{len(target_groups)}个群号\n"
        else:
            summary += "📢 目标群号：未配置（将不会进行推送）\n"

        # 数据源 - 适配新的细粒度配置结构
        data_sources = self.config.get("data_sources", {})
        active_sources = []

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

        summary += f"\n📡 活跃数据源：{len(active_sources)} 个\n"
        for source in active_sources[:5]:
            summary += f"  • {self._format_source_name(source)}\n"
        if len(active_sources) > 5:
            summary += f"  ...等{len(active_sources)}个数据源\n"

        # 阈值设置
        thresholds = self.config.get("earthquake_thresholds", {})
        if thresholds:
            summary += "\n📊 阈值设置：\n"
            if "min_magnitude" in thresholds:
                summary += f"  • 最小震级：M{thresholds['min_magnitude']}\n"
            if "min_intensity" in thresholds:
                summary += f"  • 最小烈度：{thresholds['min_intensity']}\n"
            if "min_scale" in thresholds:
                summary += f"  • 最小震度：{thresholds['min_scale']}\n"

        # 推送频率
        freq_control = self.config.get("push_frequency_control", {})
        if freq_control:
            summary += f"\n⏱️ 推送频率：每{freq_control.get('push_every_n_reports', 3)}报推送一次\n"

        summary += "\n💡 提示：详细配置请通过WebUI进行修改"
        return summary

    @filter.command("灾害预警日志")
    async def disaster_logs(self, event: AstrMessageEvent):
        """查看原始消息日志信息"""
        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            log_summary = self.disaster_service.message_logger.get_log_summary()

            if not log_summary["enabled"]:
                yield event.plain_result(
                    "📋 原始消息日志功能未启用\n\n使用 /灾害预警日志开关 启用日志记录"
                )
                return

            if not log_summary["log_exists"]:
                yield event.plain_result(
                    "📋 暂无日志记录\n\n当日志功能启用后，所有接收到的原始消息将被记录。"
                )
                return

            log_info = f"""📊 原始消息日志统计

📁 日志文件：{log_summary["log_file"]}
📈 总条目数：{log_summary["total_entries"]}
📦 文件大小：{log_summary.get("file_size_mb", 0):.2f} MB
📅 时间范围：{log_summary["date_range"]["start"]} 至 {log_summary["date_range"]["end"]}

📡 数据源统计："""

            for source in log_summary["data_sources"]:
                log_info += f"\n  • {source}"

            log_info += "\n\n💡 提示：使用 /灾害预警日志开关 可以关闭日志记录"

            yield event.plain_result(log_info)

        except Exception as e:
            logger.error(f"[灾害预警] 获取日志信息失败: {e}")
            yield event.plain_result(f"❌ 获取日志信息失败: {str(e)}")

    @filter.command("灾害预警日志开关")
    async def toggle_message_logging(self, event: AstrMessageEvent):
        """开关原始消息日志记录"""
        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            current_state = self.disaster_service.message_logger.enabled
            new_state = not current_state

            # 更新配置
            self.config["debug_config"]["enable_raw_message_logging"] = new_state
            self.disaster_service.message_logger.enabled = new_state

            # 保存配置
            self.config.save_config()

            status = "启用" if new_state else "禁用"
            action = "开始" if new_state else "停止"

            yield event.plain_result(
                f"✅ 原始消息日志记录已{status}\n\n插件将{action}记录所有数据源的原始消息格式。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 切换日志状态失败: {e}")
            yield event.plain_result(f"❌ 切换日志状态失败: {str(e)}")

    @filter.command("灾害预警日志清除")
    async def clear_message_logs(self, event: AstrMessageEvent):
        """清除所有原始消息日志"""
        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            self.disaster_service.message_logger.clear_logs()
            yield event.plain_result(
                "✅ 所有原始消息日志已清除\n\n日志文件已被删除，新的消息记录将重新开始。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 清除日志失败: {e}")
            yield event.plain_result(f"❌ 清除日志失败: {str(e)}")

    @filter.command("灾害预警去重统计")
    async def deduplication_stats(self, event: AstrMessageEvent):
        """查看事件去重统计信息"""
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 去重功能不可用")
            return

        try:
            stats = self.disaster_service.message_manager.deduplicator.get_deduplication_stats()

            stats_text = f"""📊 事件去重统计

⏱️ 时间窗口：{stats["time_window_minutes"]} 分钟
📏 位置容差：{stats["location_tolerance_km"]} 公里
📊 震级容差：{stats["magnitude_tolerance"]} 级

📈 当前记录：{stats["recent_events_count"]} 个事件

💡 说明：
• 同一地震事件只推送最先接收到信息的数据源
• 时间窗口内（1分钟）的相似事件会被去重
• 位置差异在20公里内视为同一事件
• 震级差异在0.5级内视为同一事件"""

            yield event.plain_result(stats_text)

        except Exception as e:
            logger.error(f"[灾害预警] 获取去重统计失败: {e}")
            yield event.plain_result(f"❌ 获取去重统计失败: {str(e)}")

    def _format_source_name(self, source_key: str) -> str:
        """格式化数据源名称 - 新的细粒度配置结构"""
        # 新的配置格式：service.source (如：fan_studio.china_earthquake_warning)
        service, source = source_key.split(".", 1)
        source_names = {
            "fan_studio": {
                "china_earthquake_warning": "中国地震网地震预警",
                "taiwan_cwa_earthquake": "台湾中央气象署强震即时警报",
                "china_cenc_earthquake": "中国地震台网地震测定",
                "japan_jma_earthquake": "日本气象厅地震情报",
                "usgs_earthquake": "USGS地震测定",
                "china_weather_alarm": "中国气象局气象预警",
                "china_tsunami": "自然资源部海啸预警",
            },
            "p2p_earthquake": {
                "japan_jma_eew": "P2P-日本气象厅紧急地震速报",
                "japan_jma_earthquake": "P2P-日本气象厅地震情报",
                "japan_jma_tsunami": "P2P-日本气象厅海啸预报",
            },
            "wolfx": {
                "japan_jma_eew": "Wolfx-日本气象厅紧急地震速报",
                "china_cenc_eew": "Wolfx-中国地震台网预警",
                "taiwan_cwa_eew": "Wolfx-台湾地震预警",
                "japan_jma_earthquake": "Wolfx-日本气象厅地震情报",
                "china_cenc_earthquake": "Wolfx-中国地震台网地震测定",
            },
            "global_quake": {
                "primary_server": "Global Quake主服务器",
                "secondary_server": "Global Quake备用服务器",
            },
        }
        return source_names.get(service, {}).get(source, source_key)

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot加载完成时的钩子"""
        logger.info("[灾害预警] AstrBot已加载完成，灾害预警插件准备就绪")
