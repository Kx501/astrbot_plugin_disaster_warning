"""
原始消息格式记录器
用于记录所有数据源的原始消息格式，便于分析和开发
"""

import json
from datetime import datetime
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools


class MessageLogger:
    """原始消息格式记录器"""

    def __init__(self, config: dict[str, Any], plugin_name: str):
        self.config = config
        self.plugin_name = plugin_name
        self.enabled = config.get("debug_config", {}).get(
            "enable_raw_message_logging", False
        )
        self.log_file_name = config.get("debug_config", {}).get(
            "raw_message_log_path", "raw_messages.log"
        )
        self.max_size_mb = config.get("debug_config", {}).get("log_max_size_mb", 50)
        self.max_files = config.get("debug_config", {}).get("log_max_files", 5)

        # 过滤配置
        self.filter_heartbeat = config.get("debug_config", {}).get(
            "filter_heartbeat_messages", True
        )
        self.filter_types = config.get("debug_config", {}).get(
            "filtered_message_types",
            [
                "heartbeat",
                "ping",
                "pong",  # 移除 "initial" 和 "update"，因为实际数据消息使用这些类型
            ],
        )

        # 新增过滤规则
        self.filter_p2p_areas = config.get("debug_config", {}).get(
            "filter_p2p_areas_messages", True
        )
        self.filter_duplicate_events = config.get("debug_config", {}).get(
            "filter_duplicate_events", True
        )
        self.filter_connection_status = config.get("debug_config", {}).get(
            "filter_connection_status", True
        )

        # 用于去重的缓存
        self.recent_event_hashes = set()
        self.max_cache_size = 1000

        # 日志过滤统计
        self.filter_stats = {
            "heartbeat_filtered": 0,
            "p2p_areas_filtered": 0,
            "duplicate_events_filtered": 0,
            "connection_status_filtered": 0,
            "total_filtered": 0,
        }

        # 获取插件数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.log_file_path = self.data_dir / self.log_file_name

        # 确保日志目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[灾害预警] 消息记录器初始化完成，日志文件: {self.log_file_path}")
        if self.filter_heartbeat:
            logger.info("[灾害预警] 消息过滤配置:")
            logger.info(f"  - 基础类型过滤: {self.filter_types}")
            logger.info(f"  - P2P节点状态过滤: {self.filter_p2p_areas}")
            logger.info(f"  - 重复事件过滤: {self.filter_duplicate_events}")
            logger.info(f"  - 连接状态过滤: {self.filter_connection_status}")

    def _should_filter_message(self, raw_data: Any) -> str:
        """判断是否应该过滤该消息，返回过滤原因，空字符串表示不过滤"""
        if not self.filter_heartbeat:
            return ""

        try:
            # 处理不同类型的原始数据
            if isinstance(raw_data, str) and raw_data.strip():
                # 尝试解析JSON数据
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    # 如果JSON解析失败，记录调试信息但不过滤
                    logger.debug(
                        f"[灾害预警] 消息记录器 - JSON解析失败，消息前100字符: {raw_data[:100]}..."
                    )
                    return ""

                # 获取消息类型用于调试
                msg_type = data.get("type", "")
                logger.debug(
                    f"[灾害预警] 消息记录器 - 检查消息过滤，类型: {msg_type}, 数据长度: {len(raw_data)}"
                )

                # 检查消息类型
                if msg_type and msg_type.lower() in self.filter_types:
                    self.filter_stats["heartbeat_filtered"] += 1
                    logger.debug(f"[灾害预警] 消息记录器 - 消息类型过滤: {msg_type}")
                    return f"消息类型过滤: {msg_type}"

                # 检查P2P areas消息（节点状态信息）
                if self.filter_p2p_areas and self._is_p2p_areas_message(data):
                    self.filter_stats["p2p_areas_filtered"] += 1
                    logger.debug("[灾害预警] 消息记录器 - P2P节点状态消息过滤")
                    return "P2P节点状态消息"

                # 检查重复事件 - 添加详细调试信息
                if self.filter_duplicate_events:
                    event_hash = self._generate_event_hash(data)
                    is_duplicate = self._is_duplicate_event(data)
                    if is_duplicate:
                        self.filter_stats["duplicate_events_filtered"] += 1
                        logger.debug(
                            f"[灾害预警] 消息记录器 - 重复事件过滤，哈希: {event_hash}, 原因: 事件哈希已存在"
                        )
                        return f"重复事件 (哈希: {event_hash})"
                    elif event_hash:
                        logger.debug(
                            f"[灾害预警] 消息记录器 - 事件哈希生成: {event_hash}, 允许记录"
                        )

                # 检查连接状态消息
                if self.filter_connection_status and self._is_connection_status_message(
                    data
                ):
                    self.filter_stats["connection_status_filtered"] += 1
                    logger.debug("[灾害预警] 消息记录器 - 连接状态消息过滤")
                    return "连接状态消息"

                # 检查WebSocket消息内容（嵌套JSON）
                if "raw_data" in data and isinstance(data["raw_data"], str):
                    try:
                        inner_data = json.loads(data["raw_data"])
                        inner_type = inner_data.get("type", "").lower()
                        if inner_type in self.filter_types:
                            self.filter_stats["heartbeat_filtered"] += 1
                            return f"内层消息类型过滤: {inner_type}"

                        # 检查内层数据的P2P areas消息
                        if self.filter_p2p_areas and self._is_p2p_areas_message(
                            inner_data
                        ):
                            self.filter_stats["p2p_areas_filtered"] += 1
                            return "内层P2P节点状态消息"

                        # 检查内层数据的重复事件
                        if self.filter_duplicate_events and self._is_duplicate_event(
                            inner_data
                        ):
                            self.filter_stats["duplicate_events_filtered"] += 1
                            return "内层重复事件"
                    except (json.JSONDecodeError, AttributeError):
                        pass

            elif isinstance(raw_data, dict):
                # 如果raw_data已经是字典
                msg_type = raw_data.get("type", "")
                logger.debug(
                    f"[灾害预警] 消息记录器 - 检查字典类型消息，类型: {msg_type}"
                )

                if msg_type and msg_type.lower() in self.filter_types:
                    self.filter_stats["heartbeat_filtered"] += 1
                    logger.debug(f"[灾害预警] 消息记录器 - 消息类型过滤: {msg_type}")
                    return f"消息类型过滤: {msg_type}"

                # 检查P2P areas消息
                if self.filter_p2p_areas and self._is_p2p_areas_message(raw_data):
                    self.filter_stats["p2p_areas_filtered"] += 1
                    logger.debug("[灾害预警] 消息记录器 - P2P节点状态消息过滤")
                    return "P2P节点状态消息"

                # 检查重复事件 - 添加详细调试信息
                if self.filter_duplicate_events:
                    event_hash = self._generate_event_hash(raw_data)
                    is_duplicate = self._is_duplicate_event(raw_data)
                    if is_duplicate:
                        self.filter_stats["duplicate_events_filtered"] += 1
                        logger.debug(
                            f"[灾害预警] 消息记录器 - 重复事件过滤，哈希: {event_hash}"
                        )
                        return f"重复事件 (哈希: {event_hash})"

                # 检查连接状态消息
                if self.filter_connection_status and self._is_connection_status_message(
                    raw_data
                ):
                    self.filter_stats["connection_status_filtered"] += 1
                    logger.debug("[灾害预警] 消息记录器 - 连接状态消息过滤")
                    return "连接状态消息"

        except (json.JSONDecodeError, KeyError, TypeError):
            # 如果解析失败，不过滤
            pass

        return ""

    def _is_p2p_areas_message(self, data: dict[str, Any]) -> bool:
        """判断是否为P2P areas消息（节点状态信息）"""
        # P2P消息通常包含areas数组，记录各个ID的peer数量
        if "areas" in data and isinstance(data["areas"], list):
            # 检查areas数组的内容，如果主要是peer数量信息，则过滤
            areas = data["areas"]
            if areas and all(
                isinstance(area, dict) and "peer" in area for area in areas[:3]
            ):
                return True
        return False

    def _is_duplicate_event(self, data: dict[str, Any]) -> bool:
        """判断是否为重复事件"""
        try:
            # 生成事件哈希（基于关键字段）
            event_hash = self._generate_event_hash(data)
            if event_hash in self.recent_event_hashes:
                return True

            # 添加到缓存（LRU风格）
            if len(self.recent_event_hashes) >= self.max_cache_size:
                # 移除最旧的条目（简单实现）
                self.recent_event_hashes.pop()
            self.recent_event_hashes.add(event_hash)

            return False

        except Exception:
            return False

    def _generate_event_hash(self, data: dict[str, Any]) -> str:
        """生成事件哈希用于去重 - 智能识别事件类型，避免误判"""
        # 基于事件的关键字段生成哈希
        hash_parts = []

        # 首先进行事件类型智能识别
        event_type = self._detect_event_type(data)
        hash_parts.append(f"etype:{event_type}")

        # 不同类型的事件使用不同的去重策略
        if event_type == "weather":
            # 气象预警：主要基于ID和时间
            return self._generate_weather_hash(data, hash_parts)
        elif event_type == "earthquake":
            # 地震事件：基于位置、震级、时间的综合判断
            return self._generate_earthquake_hash(data, hash_parts)
        elif event_type == "tsunami":
            # 海啸预警：基于区域和时间
            return self._generate_tsunami_hash(data, hash_parts)
        else:
            # 其他类型：使用通用哈希
            return self._generate_generic_hash(data, hash_parts)

    def _detect_event_type(self, data: dict[str, Any]) -> str:
        """智能检测事件类型"""
        # 检查消息类型字段
        msg_type = str(data.get("type", "")).lower()

        # 使用msg_type进行事件类型判断
        if msg_type in ["weather", "alarm", "warning"]:
            return "weather"
        elif msg_type in ["earthquake", "seismic"]:
            return "earthquake"
        elif msg_type in ["tsunami"]:
            return "tsunami"

        # 检查其他关键字段
        data_str = str(data).lower()

        # 气象预警特征
        if any(
            keyword in data_str
            for keyword in ["weather", "alarm", "预警", "warning", "headline"]
        ):
            if (
                "地震" not in data_str
                and "earthquake" not in data_str
                and "magnitude" not in data_str
            ):
                return "weather"

        # 地震事件特征
        if any(
            keyword in data_str
            for keyword in [
                "earthquake",
                "地震",
                "magnitude",
                "震级",
                "hypocenter",
                "震源",
            ]
        ):
            return "earthquake"

        # 海啸预警特征
        if any(keyword in data_str for keyword in ["tsunami", "海啸", "津波"]):
            return "tsunami"

        # P2P地震信息
        if "code" in data and isinstance(data.get("code"), int):
            code = data["code"]
            if code in [551, 552, 556]:  # 地震情報、津波予報、緊急地震速報
                return "earthquake" if code in [551, 556] else "tsunami"

        # 默认返回通用类型
        return "generic"

    def _generate_weather_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成气象预警哈希"""
        # 气象预警主要基于ID和发布时间
        event_id = (
            data.get("id") or data.get("headline", "")[:50]
        )  # 使用前50个字符作为ID
        if event_id:
            hash_parts.append(f"weather_id:{event_id}")

        # 添加发布时间（精确到小时）
        time_info = data.get("effective") or data.get("issue_time") or data.get("time")
        if time_info:
            try:
                if isinstance(time_info, str) and len(time_info) >= 13:
                    # 取到小时级别
                    time_key = time_info[:13]
                    hash_parts.append(f"weather_time:{time_key}")
            except Exception:
                pass

        return "|".join(hash_parts) if hash_parts else ""

    def _generate_earthquake_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成地震事件哈希 - 更宽松的精度"""
        # 检查是否有事件ID
        event_id = data.get("id") or data.get("eventId") or data.get("EventID")
        if event_id:
            hash_parts.append(f"eq_id:{event_id}")
            # 如果有ID，可以返回，因为ID通常是唯一的
            return "|".join(hash_parts)

        # 检查时间信息 - 使用更粗的粒度（10分钟窗口）
        time_info = data.get("shockTime") or data.get("time") or data.get("OriginTime")
        if time_info:
            try:
                if isinstance(time_info, str):
                    # 解析时间并量化到10分钟级别
                    time_obj = self._parse_datetime_for_hash(time_info)
                    if time_obj:
                        # 量化到10分钟级别
                        minute_rounded = (time_obj.minute // 10) * 10
                        time_key = f"{time_obj.year}{time_obj.month:02d}{time_obj.day:02d}{time_obj.hour:02d}{minute_rounded:02d}"
                        hash_parts.append(f"eq_time:{time_key}")
            except Exception:
                pass

        # 检查位置信息 - 使用更宽松的精度（0.5度，约55km）
        lat = data.get("latitude") or data.get("Latitude")
        lon = data.get("longitude") or data.get("Longitude")
        if lat is not None and lon is not None:
            try:
                lat_val = float(lat)
                lon_val = float(lon)
                # 0.5度精度（约55km）
                lat_rounded = round(lat_val * 2) / 2
                lon_rounded = round(lon_val * 2) / 2
                hash_parts.append(f"eq_loc:{lat_rounded},{lon_rounded}")
            except (ValueError, TypeError):
                pass

        # 检查震级信息 - 使用整数级别
        magnitude = data.get("magnitude") or data.get("Magnitude")
        if magnitude is not None:
            try:
                mag_int = int(float(magnitude))
                hash_parts.append(f"eq_mag:{mag_int}")
            except (ValueError, TypeError):
                pass

        return "|".join(hash_parts) if hash_parts else ""

    def _generate_tsunami_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成海啸预警哈希"""
        # 基于预警区域和时间
        event_id = data.get("id") or data.get("code", "")
        if event_id:
            hash_parts.append(f"tsunami_id:{event_id}")

        # 添加发布时间（精确到小时）
        time_info = data.get("issue_time") or data.get("time") or data.get("effective")
        if time_info:
            try:
                if isinstance(time_info, str) and len(time_info) >= 13:
                    time_key = time_info[:13]
                    hash_parts.append(f"tsunami_time:{time_key}")
            except Exception:
                pass

        return "|".join(hash_parts) if hash_parts else ""

    def _generate_generic_hash(self, data: dict[str, Any], hash_parts: list) -> str:
        """生成通用哈希"""
        # 回退到基础字段
        event_id = data.get("id") or data.get("eventId") or data.get("EventID")
        if event_id:
            hash_parts.append(f"generic_id:{event_id}")

        return "|".join(hash_parts) if hash_parts else ""

    def _parse_datetime_for_hash(self, time_str: str) -> datetime | None:
        """解析时间字符串用于哈希生成 - 更宽松的解析"""
        if not time_str:
            return None

        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _is_connection_status_message(self, data: dict[str, Any]) -> bool:
        """判断是否为连接状态消息"""
        # 检查是否为连接建立、断开等状态消息
        msg_type = data.get("type", "").lower()
        if msg_type in ["connect", "disconnect", "connection", "status"]:
            return True

        # 检查是否包含连接相关的关键词
        connection_keywords = [
            "connected",
            "disconnected",
            "connection",
            "status",
            "online",
            "offline",
        ]
        message_str = str(data).lower()
        if any(keyword in message_str for keyword in connection_keywords):
            # 进一步检查，确保不是实际的灾害事件
            disaster_keywords = [
                "earthquake",
                "地震",
                "震级",
                "magnitude",
                "tsunami",
                "海啸",
                "weather",
                "气象",
            ]
            if not any(keyword in message_str for keyword in disaster_keywords):
                return True

        return False

    def _format_readable_log(self, log_entry: dict[str, Any]) -> str:
        """格式化可读性强的日志内容"""
        try:
            # 基础信息格式化
            timestamp = datetime.fromisoformat(log_entry["timestamp"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            source = log_entry["source"]
            message_type = log_entry["message_type"]

            # 构建可读性强的日志头部
            log_content = f"\n{'=' * 40}\n"
            log_content += f"🕐 日志写入时间: {timestamp}\n"
            log_content += f"📡 来源: {source}\n"
            log_content += f"📋 类型: {message_type}\n"

            # 添加连接信息（如果有）
            connection_info = log_entry.get("connection_info", {})
            if connection_info:
                log_content += "🔗 连接: "
                if "url" in connection_info:
                    log_content += f"URL: {connection_info['url']}"
                elif "server" in connection_info and "port" in connection_info:
                    log_content += (
                        f"服务器: {connection_info['server']}:{connection_info['port']}"
                    )
                log_content += "\n"

            # 格式化原始数据
            raw_data = log_entry["raw_data"]
            log_content += "\n📊 原始数据:\n"

            # 根据数据类型进行不同的格式化
            if isinstance(raw_data, str):
                # 尝试解析JSON字符串
                try:
                    parsed_data = json.loads(raw_data)
                    log_content += self._format_json_data(parsed_data, indent=2)
                except json.JSONDecodeError:
                    # 如果不是JSON，直接显示
                    log_content += f"  {raw_data}\n"
            elif isinstance(raw_data, dict):
                # 已经是字典格式
                log_content += self._format_json_data(raw_data, indent=2)
            else:
                # 其他格式
                log_content += f"  {str(raw_data)}\n"

            # 添加插件信息
            log_content += (
                f"\n🔧 插件版本: {log_entry.get('plugin_version', 'unknown')}\n"
            )
            log_content += f"{'=' * 40}\n"

            return log_content

        except Exception as e:
            # 如果格式化失败，回退到简单的JSON格式
            logger.warning(f"[灾害预警] 日志格式化失败，使用回退格式: {e}")
            return json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n\n"

    def _format_json_data(self, data: dict[str, Any], indent: int = 0) -> str:
        """递归格式化JSON数据，增加可读性"""
        result = ""
        indent_str = "  " * indent

        for key, value in data.items():
            # 键名翻译和格式化
            key_display = self._get_display_key(key)

            if isinstance(value, dict):
                result += f"{indent_str}📋 {key_display}:\n"
                result += self._format_json_data(value, indent + 1)
            elif isinstance(value, list):
                if len(value) > 0:
                    result += f"{indent_str}📋 {key_display} ({len(value)}项):\n"
                    for i, item in enumerate(value[:5]):  # 只显示前5项
                        if isinstance(item, dict):
                            result += f"{indent_str}  [{i + 1}]:\n"
                            result += self._format_json_data(item, indent + 2)
                        else:
                            result += f"{indent_str}  [{i + 1}]: {item}\n"
                    if len(value) > 5:
                        result += f"{indent_str}  ... 还有 {len(value) - 5} 项\n"
                else:
                    result += f"{indent_str}📋 {key_display}: []\n"
            else:
                # 格式化具体值
                value_display = self._format_value(key, value)
                result += f"{indent_str}📋 {key_display}: {value_display}\n"

        return result

    def _get_display_key(self, key: str) -> str:
        """获取格式化的键名显示"""
        key_mappings = {
            # P2P相关
            "code": "消息代码",
            "earthquake": "地震信息",
            "hypocenter": "震源信息",
            "magnitude": "震级",
            "depth": "深度(km)",
            "latitude": "纬度",
            "longitude": "经度",
            "name": "地点名称",
            "time": "发生时间",
            "maxScale": "最大震度(原始)",
            "domesticTsunami": "日本境内海啸",
            "foreignTsunami": "海外海啸",
            # JMA相关
            "EventID": "事件ID",
            "OriginTime": "发震时间",
            "Hypocenter": "震源地名",
            "MaxIntensity": "最大震度",
            "Serial": "报序号",
            "AnnouncedTime": "发布时间",
            "isFinal": "最终报",
            "isCancel": "取消报",
            # 通用
            "id": "ID",
            "_id": "数据库ID",
            "type": "消息类型",
            "title": "标题",
            "source": "数据来源",
            "status": "状态",
            "issue": "发布信息",
            "correct": "订正信息",
            "placeName": "地名",
            "shockTime": "发震时间",
            "createTime": "创建时间",
            "infoTypeName": "信息类型",
            "updates": "更新次数",
            "is_training": "训练模式",
            # 连接信息
            "url": "连接地址",
            "connection_type": "连接类型",
            "server": "服务器",
            "port": "端口",
            "status_code": "状态码",
        }

        return key_mappings.get(key, key)

    def _format_value(self, key: str, value: Any) -> str:
        """格式化具体值"""
        if value is None:
            return "无数据"
        elif value == "":
            return "空字符串"
        elif isinstance(value, (int, float)):
            # 特殊数值格式化
            if key == "maxScale" and isinstance(value, int):
                scale_map = {
                    10: "震度1",
                    20: "震度2",
                    30: "震度3",
                    40: "震度4",
                    45: "震度5弱",
                    50: "震度5強",
                    55: "震度6弱",
                    60: "震度6強",
                    70: "震度7",
                }
                return f"{value} ({scale_map.get(value, '未知')})"
            elif key in ["magnitude", "Magnitude"] and isinstance(value, (int, float)):
                return f"M{value}"
            elif key in ["depth", "Depth"] and isinstance(value, (int, float)):
                return f"{value}km"
            else:
                return str(value)
        elif isinstance(value, str):
            # 字符串长度控制
            if len(value) > 50:
                return f"{value[:47]}..."
            return value
        else:
            return str(value)

    def log_raw_message(
        self,
        source: str,
        message_type: str,
        raw_data: Any,
        connection_info: dict | None = None,
    ):
        """记录原始消息（优化可读性格式 + 异常回退机制）"""
        if not self.enabled:
            return

        try:
            # 检查是否应该过滤该消息
            filter_reason = self._should_filter_message(raw_data)
            if filter_reason:
                logger.debug(
                    f"[灾害预警] 过滤消息 - 来源: {source}, 类型: {message_type}, 原因: {filter_reason}"
                )
                self.filter_stats["total_filtered"] += 1
                return

            # 获取当前时间
            current_time = datetime.now()

            # 准备日志条目数据
            log_entry = {
                "timestamp": current_time.isoformat(),
                "source": source,
                "message_type": message_type,
                "raw_data": raw_data,
                "connection_info": connection_info or {},
                "plugin_version": "1.0.0",
            }

            # 尝试新的可读性格式化
            try:
                log_content = self._format_readable_log(log_entry)
            except Exception as format_error:
                # 如果新格式失败，回退到安全的JSON格式
                logger.warning(
                    f"[灾害预警] 可读格式失败，回退到JSON格式: {format_error}"
                )
                log_content = (
                    json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n\n"
                )

            # 确保目录存在
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入日志文件
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(log_content)

            # 检查文件大小，必要时进行轮转
            self._check_log_rotation()

        except Exception as e:
            logger.error(f"[灾害预警] 记录原始消息失败: {e}")
            logger.error(
                f"[灾害预警] 失败的消息 - 来源: {source}, 类型: {message_type}"
            )
            # 记录异常堆栈
            import traceback

            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

    def log_websocket_message(
        self, connection_name: str, message: str, url: str | None = None
    ):
        """记录WebSocket消息"""
        self.log_raw_message(
            source=f"websocket_{connection_name}",
            message_type="websocket_message",
            raw_data=message,
            connection_info={"url": url, "connection_type": "websocket"},
        )

    def log_tcp_message(self, server: str, port: int, message: str):
        """记录TCP消息"""
        logger.debug(
            f"[灾害预警] 准备记录TCP消息 - 服务器: {server}:{port}, 消息: {message[:128]}..."
        )

        # 先检查过滤情况
        filter_reason = self._should_filter_message(message)
        if filter_reason:
            logger.debug(f"[灾害预警] TCP消息被过滤 - 原因: {filter_reason}")
        else:
            logger.debug("[灾害预警] TCP消息未被过滤，将记录到日志")

        self.log_raw_message(
            source="tcp_global_quake",
            message_type="tcp_message",
            raw_data=message,
            connection_info={"server": server, "port": port, "connection_type": "tcp"},
        )

    def log_http_response(
        self, url: str, response_data: Any, status_code: int | None = None
    ):
        """记录HTTP响应"""
        self.log_raw_message(
            source="http_response",
            message_type="http_response",
            raw_data=response_data,
            connection_info={
                "url": url,
                "status_code": status_code,
                "connection_type": "http",
            },
        )

    def _check_log_rotation(self):
        """检查日志文件大小并进行轮转"""
        try:
            if not self.log_file_path.exists():
                return

            # 获取文件大小（MB）
            file_size_mb = self.log_file_path.stat().st_size / (1024 * 1024)

            if file_size_mb > self.max_size_mb:
                self._rotate_logs()

        except Exception as e:
            logger.error(f"[灾害预警] 日志轮转检查失败: {e}")

    def _rotate_logs(self):
        """轮转日志文件"""
        try:
            # 关闭当前日志文件
            for i in range(self.max_files - 1, 0, -1):
                old_file = self.log_file_path.with_suffix(f".log.{i}")
                new_file = self.log_file_path.with_suffix(f".log.{i + 1}")

                if old_file.exists():
                    if new_file.exists():
                        new_file.unlink()  # 删除最旧的文件
                    old_file.rename(new_file)

            # 重命名当前日志文件
            if self.log_file_path.exists():
                backup_file = self.log_file_path.with_suffix(".log.1")
                if backup_file.exists():
                    backup_file.unlink()
                self.log_file_path.rename(backup_file)

            logger.info(f"[灾害预警] 日志文件已轮转，备份文件: {backup_file}")

        except Exception as e:
            logger.error(f"[灾害预警] 日志轮转失败: {e}")

    def get_log_summary(self) -> dict[str, Any]:
        """获取日志统计信息（支持新可读性格式）"""
        try:
            if not self.log_file_path.exists():
                return {"enabled": self.enabled, "log_exists": False}

            # 统计日志条目
            entry_count = 0
            sources = set()
            date_range = {"start": None, "end": None}
            file_size_mb = self.log_file_path.stat().st_size / (1024 * 1024)

            # 读取文件内容
            with open(self.log_file_path, encoding="utf-8") as f:
                content = f.read()

            # 按分隔符分割条目
            entries = content.split(f"\n{'=' * 40}\n")

            for entry in entries:
                entry = entry.strip()
                if not entry or not entry.startswith("🕐 时间:"):
                    continue

                entry_count += 1

                try:
                    # 提取基本信息
                    lines = entry.split("\n")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("🕐 时间:"):
                            timestamp_str = line.replace("🕐 时间:", "").strip()
                            try:
                                dt = datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                                )
                                if date_range[
                                    "start"
                                ] is None or dt < datetime.strptime(
                                    date_range["start"], "%Y-%m-%d %H:%M:%S"
                                ):
                                    date_range["start"] = timestamp_str
                                if date_range["end"] is None or dt > datetime.strptime(
                                    date_range["end"], "%Y-%m-%d %H:%M:%S"
                                ):
                                    date_range["end"] = timestamp_str
                            except ValueError:
                                pass
                        elif line.startswith("📡 来源:"):
                            source = line.replace("📡 来源:", "").strip()
                            sources.add(source)

                except Exception as e:
                    logger.debug(f"[灾害预警] 解析日志条目失败: {e}")
                    continue

            return {
                "enabled": self.enabled,
                "log_exists": True,
                "log_file": str(self.log_file_path),
                "total_entries": entry_count,
                "data_sources": list(sources),
                "date_range": date_range,
                "file_size_mb": file_size_mb,
                "filter_stats": self.filter_stats.copy(),
                "format_version": "2.0",  # 标记新格式
            }

        except Exception as e:
            logger.error(f"[灾害预警] 获取日志统计失败: {e}")
            return {"enabled": self.enabled, "log_exists": False, "error": str(e)}

    def clear_logs(self):
        """清除所有日志文件"""
        try:
            # 删除主日志文件
            if self.log_file_path.exists():
                self.log_file_path.unlink()

            # 删除轮转的旧日志文件
            for i in range(1, self.max_files + 1):
                old_file = self.log_file_path.with_suffix(f".log.{i}")
                if old_file.exists():
                    old_file.unlink()

            logger.info("[灾害预警] 所有日志文件已清除")

        except Exception as e:
            logger.error(f"[灾害预警] 清除日志失败: {e}")
