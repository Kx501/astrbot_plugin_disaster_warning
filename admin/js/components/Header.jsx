const { Box, Typography, IconButton, Chip } = MaterialUI;

/**
 * 页头组件
 * 显示当前视图标题、WebSocket 连接状态指示器和暗黑模式切换按钮
 *
 * @param {Object} props
 * @param {string} props.currentView - 当前激活的视图名称 ('status' | 'events' | 'stats' | 'config')
 */
function Header({ currentView }) {
    const { state, dispatch } = useAppContext();

    // 切换亮色/暗色主题
    const toggleTheme = () => {
        dispatch({ type: 'TOGGLE_THEME' });
    };

    // 视图标题映射
    const viewTitles = {
        'status': '运行状态',
        'events': '事件列表',
        'stats': '数据统计',
        'config': '配置管理'
    };

    return (
        <div className="top-bar">
            <Typography variant="h5" sx={{ 
                fontWeight: 800,
                color: 'text.primary',
                letterSpacing: '-0.5px'
            }}>
                {viewTitles[currentView] || '运行状态'}
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '6px 16px',
                    background: state.wsConnected ? 'rgba(76, 175, 80, 0.1)' : 'rgba(244, 67, 54, 0.1)',
                    borderRadius: '12px',
                    border: `1px solid ${state.wsConnected ? 'rgba(76, 175, 80, 0.2)' : 'rgba(244, 67, 54, 0.2)'}`
                }}>
                    <div style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: state.wsConnected ? '#4CAF50' : '#F44336',
                        boxShadow: `0 0 8px ${state.wsConnected ? '#4CAF50' : '#F44336'}`
                    }}></div>
                    <Typography variant="body2" sx={{
                        fontWeight: 600,
                        color: state.wsConnected ? '#4CAF50' : '#F44336',
                        fontSize: '13px'
                    }}>
                        {state.wsConnected ? '已连接' : '未连接'}
                    </Typography>
                </div>
                
                <IconButton 
                    onClick={toggleTheme}
                    sx={{
                        width: 44,
                        height: 44,
                        background: 'var(--md-sys-color-surface)',
                        border: '1px solid var(--glass-border)',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
                        '&:hover': { background: 'var(--md-sys-color-surface-variant)' }
                    }}
                >
                    <span style={{ fontSize: '18px' }}>
                        {state.theme === 'dark' ? '🌞' : '🌙'}
                    </span>
                </IconButton>
            </Box>
        </div>
    );
}
