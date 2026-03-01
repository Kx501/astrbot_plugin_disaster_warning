const { Typography } = MaterialUI;

function TopListCard({ title, icon, data, color, style }) {
    const safeData = (Array.isArray(data) ? data : []).map(item => {
        const count = Number(item?.count);
        return {
            ...item,
            count: Number.isFinite(count) && count >= 0 ? count : 0
        };
    });

    if (safeData.length === 0) {
        return (
            <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
                <div className="chart-card-header">
                    <span style={{ fontSize: '20px' }}>{icon}</span>
                    <Typography variant="h6">{title}</Typography>
                </div>
                <Typography variant="body2" sx={{ opacity: 0.5, textAlign: 'center', py: 4 }}>
                    暂无数据
                </Typography>
            </div>
        );
    }
    
    const maxCount = Math.max(1, ...safeData.slice(0, 10).map(d => d.count));

    return (
        <div className="card" style={{ height: '100%', minHeight: '200px', ...style }}>
            <div className="chart-card-header">
                <span style={{ fontSize: '20px' }}>{icon}</span>
                <Typography variant="h6">{title}</Typography>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {safeData.slice(0, 10).map((item, index) => {
                    const percentage = (item.count / maxCount) * 100;
                    const label = item.region || item.type || (item.source ? formatSourceName(item.source) : '未知分类');
                    
                    return (
                        <div key={index} style={{ padding: '6px 4px 8px' }}>
                            {/* 标签行 */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '5px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
                                    <div style={{
                                        width: '20px',
                                        height: '20px',
                                        borderRadius: '5px',
                                        background: index < 3 ? color : 'var(--md-sys-color-surface-variant)',
                                        color: index < 3 ? '#fff' : 'var(--md-sys-color-on-surface-variant)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: '11px',
                                        fontWeight: 700,
                                        flexShrink: 0,
                                        opacity: index < 3 ? 1 : 0.6,
                                    }}>
                                        {index + 1}
                                    </div>
                                    <Typography variant="body2" noWrap sx={{ fontWeight: 600, fontSize: '13px', flex: 1, minWidth: 0 }}>
                                        {label}
                                    </Typography>
                                </div>
                                <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.65, flexShrink: 0, ml: 1 }}>
                                    {item.count}
                                </Typography>
                            </div>
                            {/* 进度条：从 0 开始，宽度严格线性 */}
                            <div style={{
                                height: '20px',
                                borderRadius: '6px',
                                background: 'var(--md-sys-color-outline-variant)',
                                overflow: 'hidden',
                            }}>
                                <div style={{
                                    height: '100%',
                                    width: `${percentage}%`,
                                    borderRadius: '6px',
                                    background: color,
                                    opacity: index < 3 ? 0.85 : 0.5,
                                    transition: 'width 0.45s cubic-bezier(0.4, 0, 0.2, 1)',
                                }} />
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
