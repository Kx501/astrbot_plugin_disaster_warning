const { Box, TextField, Switch, FormControlLabel, Typography, Button, Accordion, AccordionSummary, AccordionDetails, Divider, Paper, Chip } = MaterialUI;
const { useState, useEffect } = React;

// 为不同配置类型定义图标
const CONFIG_ICONS = {
    enabled: '🔌',
    admin_users: '👥',
    target_sessions: '📨',
    display_timezone: '🌍',
    data_sources: '📡',
    earthquake_filters: '🔍',
    local_monitoring: '📍',
    message_format: '💬',
    push_frequency_control: '⏱️',
    strategies: '🎯',
    telemetry_config: '📊',
    weather_config: '⛈️',
    web_admin: '💻',
    websocket_config: '🔌',
    debug_config: '🐛'
};

/**
 * 配置字段渲染组件
 * 根据后端返回的 Schema 动态渲染不同类型的输入控件
 *
 * @param {Object} props
 * @param {string} props.fieldKey - 字段键名
 * @param {Object} props.schema - 字段 Schema 定义
 * @param {any} props.value - 当前值
 * @param {Function} props.onChange - 值变更回调
 * @param {number} props.depth - 嵌套深度 (用于缩进和样式)
 */
function ConfigField({ fieldKey, schema, value, onChange, depth = 0 }) {
    const [localValue, setLocalValue] = useState(value);

    useEffect(() => {
        setLocalValue(value);
    }, [value]);

    const handleChange = (newValue) => {
        setLocalValue(newValue);
        onChange(newValue);
    };

    const icon = CONFIG_ICONS[fieldKey] || '⚙️';

    // 对象类型 (后端使用 'object' + 'items')
    if (schema.type === 'object' && schema.items) {
        return (
            <Paper
                elevation={depth === 0 ? 2 : 0}
                sx={{
                    my: depth === 0 ? 1 : 0.75,
                    overflow: 'hidden',
                    border: depth === 0 ? 1.5 : 1,
                    borderColor: depth === 0 ? 'primary.main' : 'divider',
                    borderLeft: depth > 0 ? '3px solid' : undefined,
                    borderLeftColor: depth > 0 ? 'primary.light' : undefined,
                    borderRadius: 2,
                    background: depth === 0
                        ? 'linear-gradient(135deg, rgba(0, 90, 193, 0.04) 0%, rgba(0, 90, 193, 0.01) 100%)'
                        : 'transparent'
                }}
            >
                <Accordion
                    defaultExpanded={false}
                    elevation={0}
                    sx={{
                        '&:before': { display: 'none' },
                        bgcolor: 'transparent'
                    }}
                >
                    <AccordionSummary
                        expandIcon={
                            <Box sx={{
                                fontSize: '14px',
                                transform: 'rotate(0deg)',
                                transition: 'transform 0.2s',
                                '.Mui-expanded &': { transform: 'rotate(180deg)' }
                            }}>
                                ▼
                            </Box>
                        }
                        sx={{
                            px: 2,
                            py: 1,
                            minHeight: '48px !important',
                            bgcolor: depth === 0 ? 'rgba(0, 90, 193, 0.06)' : depth === 1 ? 'rgba(0, 90, 193, 0.02)' : 'transparent',
                            '&:hover': {
                                bgcolor: depth === 0 ? 'rgba(0, 90, 193, 0.1)' : 'rgba(0, 90, 193, 0.05)'
                            },
                            transition: 'all 0.2s ease'
                        }}
                    >
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1 }}>
                            <Box sx={{ fontSize: depth === 0 ? '20px' : '16px' }}>{icon}</Box>
                            <Box sx={{ flex: 1 }}>
                                <Typography
                                    variant="subtitle2"
                                    sx={{
                                        fontWeight: 700,
                                        color: depth === 0 ? 'primary.main' : depth > 0 ? 'primary.dark' : 'text.primary',
                                        fontSize: depth === 0 ? '0.95rem' : '0.875rem'
                                    }}
                                >
                                    {schema.description || fieldKey}
                                </Typography>
                                {schema.hint && depth === 0 && (
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                                        {schema.hint}
                                    </Typography>
                                )}
                            </Box>
                            {depth === 0 && (
                                <Chip
                                    label={`${Object.keys(schema.items).length}项`}
                                    size="small"
                                    color="primary"
                                    variant="outlined"
                                    sx={{ height: 22, fontSize: '0.7rem' }}
                                />
                            )}
                            {depth > 0 && (
                                <Typography variant="caption" sx={{ color: 'primary.main', fontWeight: 600, mr: 0.5 }}>
                                    可展开 →
                                </Typography>
                            )}
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails sx={{ px: 2.5, py: 1.5, bgcolor: 'background.default' }}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                            {Object.entries(schema.items).map(([key, subSchema]) => (
                                <ConfigField
                                    key={key}
                                    fieldKey={key}
                                    schema={subSchema}
                                    value={localValue?.[key]}
                                    onChange={(newValue) => handleChange({ ...localValue, [key]: newValue })}
                                    depth={depth + 1}
                                />
                            ))}
                        </Box>
                    </AccordionDetails>
                </Accordion>
            </Paper>
        );
    }

    // 布尔类型 (后端使用 'bool')
    if (schema.type === 'bool' || schema.type === 'boolean') {
        return (
            <Paper
                elevation={0}
                sx={{
                    my: 0.5,
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 1.5,
                    overflow: 'hidden',
                    transition: 'all 0.2s',
                    '&:hover': {
                        borderColor: 'primary.main',
                        boxShadow: '0 1px 4px rgba(0, 90, 193, 0.1)'
                    }
                }}
            >
                <FormControlLabel
                    control={
                        <Switch
                            checked={localValue !== undefined ? localValue : (schema.default || false)}
                            onChange={(e) => handleChange(e.target.checked)}
                            sx={{
                                width: 52,
                                height: 32,
                                padding: 0,
                                '& .MuiSwitch-switchBase': {
                                    padding: 0,
                                    margin: '4px',
                                    transitionDuration: '300ms',
                                    '&.Mui-checked': {
                                        transform: 'translateX(20px)',
                                        color: '#fff',
                                        '& + .MuiSwitch-track': {
                                            backgroundColor: 'primary.main',
                                            opacity: 1,
                                            border: 0,
                                        },
                                        '& .MuiSwitch-thumb:before': {
                                            content: '"✓"',
                                            fontSize: '14px',
                                            color: 'primary.main',
                                        },
                                    },
                                },
                                '& .MuiSwitch-thumb': {
                                    boxSizing: 'border-box',
                                    width: 24,
                                    height: 24,
                                    boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)',
                                    '&:before': {
                                        content: '"×"',
                                        position: 'absolute',
                                        width: '100%',
                                        height: '100%',
                                        left: 0,
                                        top: 0,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: '16px',
                                        color: '#666',
                                        fontWeight: 'bold',
                                    },
                                },
                                '& .MuiSwitch-track': {
                                    borderRadius: 16,
                                    backgroundColor: 'rgba(0, 0, 0, 0.12)',
                                    opacity: 1,
                                    transition: 'background-color 300ms',
                                },
                            }}
                        />
                    }
                    label={
                        <Box>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {schema.description || fieldKey}
                            </Typography>
                            {schema.hint && (
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                                    {schema.hint}
                                </Typography>
                            )}
                        </Box>
                    }
                    sx={{
                        m: 0,
                        p: 1.5,
                        width: '100%',
                        display: 'flex',
                        justifyContent: 'space-between'
                    }}
                />
            </Paper>
        );
    }

    // 列表类型 (后端使用 'list')
    if (schema.type === 'list' || schema.type === 'array') {
        return (
            <Box sx={{ my: 1.5 }}>
                <Box sx={{ mb: 0.75, display: 'flex', alignItems: 'center', gap: 0.75 }}>
                    <Box
                        sx={{
                            width: 3,
                            height: 16,
                            bgcolor: 'primary.main',
                            borderRadius: 0.5
                        }}
                    />
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'primary.main', fontSize: '0.875rem' }}>
                        {schema.description || fieldKey}
                    </Typography>
                </Box>
                {schema.hint && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, pl: 1.5 }}>
                        {schema.hint}
                    </Typography>
                )}
                <TextField
                    fullWidth
                    multiline
                    rows={3}
                    size="small"
                    value={Array.isArray(localValue) ? localValue.join('\n') : ''}
                    onChange={(e) => handleChange(e.target.value.split('\n').map(s => s.trim()).filter(Boolean))}
                    placeholder="每行一项"
                    variant="outlined"
                    sx={{
                        '& .MuiOutlinedInput-root': {
                            borderRadius: 1.5,
                            bgcolor: 'background.paper',
                            fontSize: '0.875rem',
                            '&:hover': {
                                '& > fieldset': { borderColor: 'primary.main' }
                            },
                            '&.Mui-focused': {
                                bgcolor: 'background.default',
                                '& > fieldset': {
                                    borderWidth: 2,
                                    borderColor: 'primary.main'
                                }
                            }
                        }
                    }}
                />
            </Box>
        );
    }

    // 字符串类型(默认)
    // 判断是否应该使用多行输入
    const shouldBeMultiline =
        (schema.hint && schema.hint.length > 50) ||
        fieldKey.includes('format') ||
        fieldKey.includes('template') ||
        fieldKey.includes('pattern') ||
        fieldKey.includes('message') ||
        fieldKey.includes('body') ||
        fieldKey.includes('content');

    return (
        <Box sx={{ my: 1.5 }}>
            <Box sx={{ mb: 0.75, display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Box
                    sx={{
                        width: 3,
                        height: 16,
                        bgcolor: 'primary.main',
                        borderRadius: 0.5
                    }}
                />
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'primary.main', fontSize: '0.875rem' }}>
                    {schema.description || fieldKey}
                </Typography>
            </Box>
            {schema.hint && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, pl: 1.5 }}>
                    {schema.hint}
                </Typography>
            )}
            <TextField
                fullWidth
                size="small"
                multiline={shouldBeMultiline}
                rows={shouldBeMultiline ? 3 : undefined}
                value={localValue !== undefined ? localValue : (schema.default || '')}
                onChange={(e) => handleChange(e.target.value)}
                variant="outlined"
                sx={{
                    '& .MuiOutlinedInput-root': {
                        borderRadius: 1.5,
                        bgcolor: 'background.paper',
                        fontSize: '0.875rem',
                        '&:hover': {
                            '& > fieldset': { borderColor: 'primary.main' }
                        },
                        '&.Mui-focused': {
                            bgcolor: 'background.default',
                            '& > fieldset': {
                                borderWidth: 2,
                                borderColor: 'primary.main'
                            }
                        }
                    }
                }}
            />
        </Box>
    );
}

/**
 * 主配置渲染器组件
 * 负责加载、显示和保存插件的完整配置
 * 包含了配置的获取、状态管理和保存逻辑
 */
function ConfigRenderer() {
    const [schema, setSchema] = useState(null);
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const api = useApi();

    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        try {
            const [schemaData, configData] = await Promise.all([
                api.getConfigSchema(),
                api.getFullConfig()
            ]);
            console.log('[ConfigRenderer] Schema:', schemaData);
            console.log('[ConfigRenderer] Config:', configData);
            setSchema(schemaData);
            setConfig(configData);
        } catch (e) {
            console.error('加载配置失败', e);
            alert('加载配置失败,请检查控制台');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await api.updateConfig(config);
            alert('✅ 配置已保存');
        } catch (e) {
            console.error('保存配置失败', e);
            alert('❌ 保存配置失败,请检查控制台');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <Box sx={{ textAlign: 'center', py: 6 }}>
                <Box sx={{ fontSize: '36px', mb: 1.5 }}>⚙️</Box>
                <Typography variant="body1" color="text.secondary">加载配置中...</Typography>
            </Box>
        );
    }

    if (!schema || !config) {
        return (
            <Box sx={{ textAlign: 'center', py: 6 }}>
                <Box sx={{ fontSize: '36px', mb: 1.5 }}>❌</Box>
                <Typography variant="body1" color="error">无法加载配置</Typography>
            </Box>
        );
    }

    return (
        <Box>
            {/* 配置项列表 */}
            <Box sx={{
                maxHeight: '65vh',
                overflowY: 'auto',
                px: 1.5,
                py: 0.5,
                '&::-webkit-scrollbar': {
                    width: '6px',
                },
                '&::-webkit-scrollbar-track': {
                    bgcolor: 'background.default',
                    borderRadius: 3,
                },
                '&::-webkit-scrollbar-thumb': {
                    bgcolor: 'primary.main',
                    borderRadius: 3,
                    '&:hover': {
                        bgcolor: 'primary.dark',
                    }
                }
            }}>
                {Object.entries(schema).map(([key, subSchema]) => (
                    <ConfigField
                        key={key}
                        fieldKey={key}
                        schema={subSchema}
                        value={config[key]}
                        onChange={(newValue) => setConfig({ ...config, [key]: newValue })}
                    />
                ))}
            </Box>

            {/* 底部操作栏 */}
            <Box sx={{
                position: 'sticky',
                bottom: 0,
                bgcolor: 'background.paper',
                borderTop: 2,
                borderColor: 'primary.main',
                mt: 1.5,
                px: 2.5,
                py: 2,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                boxShadow: '0 -2px 8px rgba(0, 0, 0, 0.08)'
            }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
                    {Object.keys(schema).length} 个配置组
                </Typography>
                <Box sx={{ display: 'flex', gap: 1.5 }}>
                    <Button
                        onClick={loadConfig}
                        disabled={saving}
                        variant="outlined"
                        size="medium"
                        startIcon={<span>🔄</span>}
                        sx={{
                            minWidth: 100,
                            borderRadius: 2,
                            borderWidth: 1.5,
                            fontSize: '0.875rem',
                            '&:hover': { borderWidth: 1.5 }
                        }}
                    >
                        重置
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleSave}
                        disabled={saving}
                        size="medium"
                        startIcon={<span>💾</span>}
                        sx={{
                            minWidth: 120,
                            borderRadius: 2,
                            fontSize: '0.875rem',
                            boxShadow: '0 2px 8px rgba(0, 90, 193, 0.3)',
                            '&:hover': {
                                boxShadow: '0 4px 12px rgba(0, 90, 193, 0.4)',
                            }
                        }}
                    >
                        {saving ? '保存中...' : '保存配置'}
                    </Button>
                </Box>
            </Box>
        </Box>
    );
}
