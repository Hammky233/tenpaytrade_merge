// 财付通交易流水处理工具 v4.0 — React 前端

const { useState, useEffect, useRef, useCallback } = React;

// ========== API 封装 ==========
const api = window.pywebview?.api;

async function callApi(method, ...args) {
    if (!api) {
        // 浏览器开发模式 fallback
        console.warn("pywebview API 不可用，使用模拟数据");
        return mockApi(method, ...args);
    }
    return api[method](...args);
}

// 开发模式的模拟 API（在浏览器中调试用）
function mockApi(method, ...args) {
    switch(method) {
        case 'select_folder': return prompt("模拟选择文件夹", "C:/data/source") || "";
        case 'select_file': return prompt("模拟选择文件", "C:/data/batch.xlsx") || "";
        case 'select_files': return prompt("模拟多选文件（|分隔）", "file1.xlsx|file2.xlsx") || "";
        case 'get_file_info': return { rows: 0, cols: 0, filename: args[0]?.split('/').pop() || "" };
        case 'start_batch_process': return "started";
        case 'start_merge_process': return "started";
        case 'get_batch_status': return {
            status: "idle", total: 0, current: 0, success: 0, fail: 0, skipped: 0, logs: [], result: {}
        };
        default: return null;
    }
}

// ========== 工具函数 ==========

async function copyLogsToClipboard(logs) {
    const text = logs.join("\n");
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        // fallback: 创建临时 textarea
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
    }
}

/** 将 HH:MM 字符串转为分钟数，失败返回 -1。自动归一化中英文冒号 */
function parseTime(timeStr) {
    if (!timeStr || typeof timeStr !== "string") return -1;
    // 归一化冒号：全角（中文输入法）→ 半角
    const cleaned = timeStr.trim().replace(/：/g, ":");
    const parts = cleaned.split(":");
    if (parts.length < 2) return -1;
    const h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    if (isNaN(h) || isNaN(m)) return -1;
    return h * 60 + m;
}

// ========== 组件 ==========

// --- 单批次清洗 Tab ---
function BatchTab() {
    const [source, setSource] = useState("");
    const [output, setOutput] = useState("");
    const [outputName, setOutputName] = useState("Tenpay_merge.xlsx");
    const [status, setStatus] = useState({ status: "idle", logs: [] });
    const [running, setRunning] = useState(false);
    const timerRef = useRef(null);

    // 轮询状态
    useEffect(() => {
        if (!running) return;
        timerRef.current = setInterval(async () => {
            const s = await callApi('get_batch_status');
            setStatus(s);
            if (s.status === "done" || s.status === "error") {
                setRunning(false);
            }
        }, 300);
        return () => clearInterval(timerRef.current);
    }, [running]);

    const handleSelectSource = async () => {
        const path = await callApi('select_folder');
        if (path) setSource(path);
    };

    const handleSelectOutput = async () => {
        const path = await callApi('select_folder');
        if (path) setOutput(path);
    };

    const handleStart = async () => {
        if (!source || !output) return;
        setStatus({ status: "running", total: 0, current: 0, success: 0, fail: 0, skipped: 0, logs: [], result: {} });
        setRunning(true);
        const result = await callApi('start_batch_process', source, output, outputName);
        if (result !== "started") {
            setStatus(s => ({ ...s, status: "error", logs: [...s.logs, `❌ ${result}`] }));
            setRunning(false);
        }
    };

    const total = status.total || 0;
    const done = status.current || 0;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;

    return (
        <div>
            {/* 配置区 */}
            <div className="card">
                <div className="card-title">📂 单批次清洗配置</div>
                <div className="form-row">
                    <span className="form-label">数据源文件夹</span>
                    <input className="form-input" value={source} readOnly placeholder="点击右侧按钮选择..." />
                    <button className="btn btn-secondary" onClick={handleSelectSource} disabled={running}>选择</button>
                </div>
                <div className="form-row">
                    <span className="form-label">输出文件夹</span>
                    <input className="form-input" value={output} readOnly placeholder="点击右侧按钮选择..." />
                    <button className="btn btn-secondary" onClick={handleSelectOutput} disabled={running}>选择</button>
                </div>
                <div className="form-row">
                    <span className="form-label">输出文件名</span>
                    <input
                        className="form-input"
                        value={outputName}
                        onChange={e => setOutputName(e.target.value)}
                        disabled={running}
                        placeholder="Tenpay_merge.xlsx"
                    />
                </div>
                <div style={{textAlign: "center", marginTop: 12}}>
                    <button className="btn btn-primary btn-lg" onClick={handleStart}
                            disabled={running || !source || !output}>
                        {running ? "⏳ 处理中..." : "🚀 开始处理"}
                    </button>
                </div>
            </div>

            {/* 进度 */}
            {(running || status.status === "done" || status.status === "error") && (
                <div className="card">
                    <div className="card-title">📊 处理进度</div>
                    <div className="progress-container">
                        <div className="progress-bar">
                            <div className="progress-fill" style={{width: `${pct}%`}} />
                        </div>
                    </div>
                    <div className="progress-stats">
                        <span className="stat">进度: <b>{done}/{total}</b></span>
                        <span className="stat">✅ <span className="stat-ok">{status.success || 0}</span></span>
                        <span className="stat">❌ <span className="stat-fail">{status.fail || 0}</span></span>
                        <span className="stat">⏭️ <span className="stat-skip">{status.skipped || 0}</span></span>
                    </div>
                    {status.status === "done" && status.result && (
                        <div style={{marginTop: 12, padding: 12, background: "#f0fdf4", borderRadius: 6, fontSize: 13}}>
                            ✅ 完成! 输出: {status.result.output}<br/>
                            📊 总记录: {status.result.rows} 行 | 耗时: {status.result.elapsed} 秒
                        </div>
                    )}
                    {status.status === "error" && (
                        <div style={{marginTop: 12, padding: 12, background: "#fef2f2", borderRadius: 6, fontSize: 13, color: "var(--danger)"}}>
                            ❌ 处理过程中出现错误，请检查日志
                        </div>
                    )}
                </div>
            )}

            {/* 日志 */}
            {status.logs && status.logs.length > 0 && (
                <div className="card">
                    <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12}}>
                        <span className="card-title" style={{marginBottom: 0}}>📋 处理日志</span>
                        <button className="btn btn-sm btn-secondary" onClick={() => copyLogsToClipboard(status.logs)}>
                            📋 复制
                        </button>
                    </div>
                    <div className="log-panel">
                        {status.logs.map((log, i) => (
                            <div key={i}>{log}</div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// --- 多批次合并 Tab ---
function MergeTab() {
    const [inputFiles, setInputFiles] = useState([]);  // [{path, rows, cols, filename}]
    const [output, setOutput] = useState("");
    const [outputName, setOutputName] = useState("merged.xlsx");
    const [status, setStatus] = useState({ status: "idle", logs: [] });
    const [running, setRunning] = useState(false);
    const timerRef = useRef(null);

    useEffect(() => {
        if (!running) return;
        timerRef.current = setInterval(async () => {
            const s = await callApi('get_batch_status');
            setStatus(s);
            if (s.status === "done" || s.status === "error") {
                setRunning(false);
            }
        }, 300);
        return () => clearInterval(timerRef.current);
    }, [running]);

    const handleAddFile = async () => {
        const paths = await callApi('select_files');
        if (!paths) return;
        const fileList = paths.split("|").filter(Boolean);
        for (const fp of fileList) {
            if (!inputFiles.find(f => f.path === fp)) {
                const info = await callApi('get_file_info', fp);
                setInputFiles(prev => [...prev, { path: fp, ...info }]);
            }
        }
    };

    const handleRemove = (path) => {
        setInputFiles(prev => prev.filter(f => f.path !== path));
    };

    const handleSelectOutput = async () => {
        const path = await callApi('select_folder');
        if (path) setOutput(path);
    };

    const handleStart = async () => {
        if (inputFiles.length === 0 || !output) return;
        const outputPath = outputName.endsWith('.xlsx') ? outputName : outputName + '.xlsx';
        const fullOutput = output + '\\' + outputPath;
        const filesStr = inputFiles.map(f => f.path).join("|");
        setRunning(true);
        setStatus({ status: "running", total: 0, current: 0, success: 0, fail: 0, skipped: 0, logs: [], result: {} });
        const result = await callApi('start_merge_process', filesStr, fullOutput);
        if (result !== "started") {
            setStatus(s => ({ ...s, status: "error", logs: [...s.logs, `❌ ${result}`] }));
            setRunning(false);
        }
    };

    const totalRows = inputFiles.reduce((sum, f) => sum + (f.rows || 0), 0);

    return (
        <div>
            {/* 文件列表 */}
            <div className="card">
                <div className="card-title">📦 批次文件列表 ({inputFiles.length} 个, 共 {totalRows} 行)</div>
                {inputFiles.length > 0 ? (
                    <div className="file-list">
                        {inputFiles.map((f, i) => (
                            <div className="file-item" key={i}>
                                <span className="file-name">📄 {f.filename || f.path.split('\\').pop().split('/').pop()}</span>
                                <span className="file-info">{f.rows} 行 · {f.cols} 列</span>
                                <button className="btn btn-danger" onClick={() => handleRemove(f.path)} disabled={running}>
                                    移除
                                </button>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div style={{padding: 20, textAlign: "center", color: "var(--text-secondary)", fontSize: 13}}>
                        尚未添加任何批次文件
                    </div>
                )}
                <button className="file-add" onClick={handleAddFile} disabled={running}>
                    + 添加批次文件
                </button>
            </div>

            {/* 输出 */}
            <div className="card">
                <div className="card-title">💾 输出设置</div>
                <div className="form-row">
                    <span className="form-label">输出文件夹</span>
                    <input className="form-input" value={output} readOnly placeholder="点击右侧按钮选择..." />
                    <button className="btn btn-secondary" onClick={handleSelectOutput} disabled={running}>选择</button>
                </div>
                <div className="form-row">
                    <span className="form-label">输出文件名</span>
                    <input
                        className="form-input"
                        value={outputName}
                        onChange={e => setOutputName(e.target.value)}
                        disabled={running}
                        placeholder="merged.xlsx"
                    />
                </div>
                <div style={{textAlign: "center", marginTop: 12}}>
                    <button className="btn btn-primary btn-lg" onClick={handleStart}
                            disabled={running || inputFiles.length === 0 || !output}>
                        {running ? "⏳ 合并中..." : "🔄 开始合并"}
                    </button>
                </div>
            </div>

            {/* 进度与日志 */}
            {status.logs && status.logs.length > 0 && (
                <div className="card">
                    <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12}}>
                        <span className="card-title" style={{marginBottom: 0}}>📋 合并进度</span>
                        <button className="btn btn-sm btn-secondary" onClick={() => copyLogsToClipboard(status.logs)}>
                            📋 复制
                        </button>
                    </div>
                    <div className="log-panel">
                        {status.logs.map((log, i) => (
                            <div key={i}>{log}</div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// --- 停车配置 Tab ---
function ParkingConfigTab() {
    const [config, setConfig] = useState(null);
    const [newInclude, setNewInclude] = useState("");
    const [newExclude, setNewExclude] = useState("");
    const [newOpponent, setNewOpponent] = useState("");
    const [saveMsg, setSaveMsg] = useState("");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadConfig();
    }, []);

    async function loadConfig() {
        setLoading(true);
        try {
            const cfg = await callApi('get_parking_config');
            if (cfg && !cfg.error) {
                setConfig(cfg);
            } else {
                setSaveMsg("加载配置失败: " + (cfg?.error || "未知错误"));
            }
        } catch (e) {
            setSaveMsg("加载配置失败: " + (e.message || e));
        }
        setLoading(false);
    }

    function addKeyword(group, value) {
        const v = value.trim();
        if (!v) return;
        if (config[group].includes(v)) return;  // 不重复添加
        setConfig(prev => ({
            ...prev,
            [group]: [...prev[group], v]
        }));
        setSaveMsg("");
    }

    function removeKeyword(group, index) {
        setConfig(prev => ({
            ...prev,
            [group]: prev[group].filter((_, i) => i !== index)
        }));
        setSaveMsg("");
    }

    async function handleSave() {
        setSaveMsg("");
        const result = await callApi('save_parking_config', config);
        if (result === "ok") {
            setSaveMsg("✅ 配置已保存");
            setTimeout(() => setSaveMsg(""), 3000);
        } else {
            setSaveMsg("❌ " + result);
        }
    }

    if (loading) {
        return <div className="card"><div style={{textAlign:"center", padding:40, color:"var(--text-secondary)"}}>加载中...</div></div>;
    }

    if (!config) {
        return <div className="card"><div style={{textAlign:"center", padding:40, color:"var(--danger)"}}>{saveMsg || "加载配置失败"}</div></div>;
    }

    const includeKw = config["备注2关键词"] || [];
    const excludeKw = config["排除关键词"] || [];
    const opponentKw = config["对手侧账户名称关键词"] || [];

    return (
        <div>
            {/* 筛选逻辑流程图 */}
            <div className="card">
                <div className="card-title">📐 停车缴费识别逻辑</div>
                <div className="logic-flow">
                    <div className="flow-row">
                        <span style={{fontWeight:600}}>📝 备注2 / 备注1</span>
                        <span style={{color:"var(--text-secondary)"}}>文本内容</span>
                    </div>
                    <div className="flow-indent">
                        <div className="flow-row">
                            <span className="flow-arrow">↓</span>
                            <span>包含任一 </span>
                            <span className="flow-label flow-label-include">包含关键词</span>
                        </div>
                        <div className="flow-row">
                            <span className="flow-arrow">↓</span>
                            <span>不包含任一 </span>
                            <span className="flow-label flow-label-exclude">排除关键词</span>
                        </div>
                    </div>
                    <div className="flow-row">
                        <span className="flow-arrow" style={{marginLeft:20}}>→</span>
                        <span className="flow-result">识别为停车缴费</span>
                        <span style={{color:"var(--text-secondary)"}}>──┐</span>
                    </div>
                    <div className="flow-branch">
                        <div className="flow-row">
                            <span style={{fontWeight:600}}>🏦 对手侧账户名称</span>
                            <span style={{color:"var(--text-secondary)"}}>文本内容</span>
                        </div>
                        <div className="flow-indent">
                            <div className="flow-row">
                                <span className="flow-arrow">↓</span>
                                <span>包含任一 </span>
                                <span className="flow-label flow-label-opponent">对手侧关键词</span>
                            </div>
                        </div>
                        <div className="flow-row">
                            <span className="flow-arrow" style={{marginLeft:20}}>→</span>
                            <span className="flow-result">识别为停车缴费</span>
                            <span style={{color:"var(--text-secondary)"}}>──┘</span>
                        </div>
                    </div>
                    <div style={{borderTop:"1px solid var(--border)", margin:"10px 0"}}></div>
                    <div className="flow-row">
                        <span className="flow-arrow">↓</span>
                        <span>合并去重 → 提取车牌号</span>
                    </div>
                    <div className="flow-indent">
                        <div className="flow-row">
                            <span>车牌提取失败 + 备注含省份简称 → </span>
                            <span className="flow-label flow-label-yellow">🟡 整行标黄</span>
                            <span style={{color:"var(--text-secondary)", fontSize:12}}>（人工复核）</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* 包含关键词 */}
            <div className="card">
                <div className="card-title">
                    <span className="flow-label flow-label-include" style={{marginRight:8}}>包含</span>
                    备注2/备注1 包含关键词
                    <span style={{fontSize:12, color:"var(--text-secondary)", fontWeight:400, marginLeft:8}}>
                        备注中包含任一关键词即识别为停车缴费候选
                    </span>
                </div>
                <div className="keyword-tags">
                    {includeKw.length === 0 ? (
                        <span className="keyword-empty">暂无关键词</span>
                    ) : (
                        includeKw.map((kw, i) => (
                            <span className="keyword-tag" key={i}>
                                {kw}
                                <span className="tag-remove" onClick={() => removeKeyword("备注2关键词", i)}>×</span>
                            </span>
                        ))
                    )}
                </div>
                <div className="keyword-input-row">
                    <input
                        className="form-input"
                        value={newInclude}
                        onChange={e => setNewInclude(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") { addKeyword("备注2关键词", newInclude); setNewInclude(""); } }}
                        placeholder="输入新关键词，回车添加"
                    />
                    <button className="btn btn-primary btn-sm" onClick={() => { addKeyword("备注2关键词", newInclude); setNewInclude(""); }}>
                        + 添加
                    </button>
                </div>
            </div>

            {/* 排除关键词 */}
            <div className="card">
                <div className="card-title">
                    <span className="flow-label flow-label-exclude" style={{marginRight:8}}>排除</span>
                    备注2/备注1 排除关键词
                    <span style={{fontSize:12, color:"var(--text-secondary)", fontWeight:400, marginLeft:8}}>
                        备注中包含任一排除关键词则跳过（即使命中了包含关键词）
                    </span>
                </div>
                <div className="keyword-tags">
                    {excludeKw.length === 0 ? (
                        <span className="keyword-empty">暂无排除关键词（不过滤）</span>
                    ) : (
                        excludeKw.map((kw, i) => (
                            <span className="keyword-tag" key={i}>
                                {kw}
                                <span className="tag-remove" onClick={() => removeKeyword("排除关键词", i)}>×</span>
                            </span>
                        ))
                    )}
                </div>
                <div className="keyword-input-row">
                    <input
                        className="form-input"
                        value={newExclude}
                        onChange={e => setNewExclude(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") { addKeyword("排除关键词", newExclude); setNewExclude(""); } }}
                        placeholder="输入要排除的关键词，回车添加"
                    />
                    <button className="btn btn-primary btn-sm" onClick={() => { addKeyword("排除关键词", newExclude); setNewExclude(""); }}>
                        + 添加
                    </button>
                </div>
            </div>

            {/* 对手侧关键词 */}
            <div className="card">
                <div className="card-title">
                    <span className="flow-label flow-label-opponent" style={{marginRight:8}}>对手侧</span>
                    对手侧账户名称 关键词
                    <span style={{fontSize:12, color:"var(--text-secondary)", fontWeight:400, marginLeft:8}}>
                        对手侧账户名称包含任一关键词即识别为停车缴费
                    </span>
                </div>
                <div className="keyword-tags">
                    {opponentKw.length === 0 ? (
                        <span className="keyword-empty">暂无关键词</span>
                    ) : (
                        opponentKw.map((kw, i) => (
                            <span className="keyword-tag" key={i}>
                                {kw}
                                <span className="tag-remove" onClick={() => removeKeyword("对手侧账户名称关键词", i)}>×</span>
                            </span>
                        ))
                    )}
                </div>
                <div className="keyword-input-row">
                    <input
                        className="form-input"
                        value={newOpponent}
                        onChange={e => setNewOpponent(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") { addKeyword("对手侧账户名称关键词", newOpponent); setNewOpponent(""); } }}
                        placeholder="输入对手侧关键词，回车添加"
                    />
                    <button className="btn btn-primary btn-sm" onClick={() => { addKeyword("对手侧账户名称关键词", newOpponent); setNewOpponent(""); }}>
                        + 添加
                    </button>
                </div>
            </div>

            {/* 保存 */}
            <div style={{textAlign: "center", marginBottom: 16}}>
                <button className="btn btn-primary btn-lg" onClick={handleSave}>
                    💾 保存配置
                </button>
                {saveMsg && (
                    <div style={{
                        marginTop: 8,
                        fontSize: 13,
                        color: saveMsg.startsWith("✅") ? "var(--success)" : "var(--danger)"
                    }}>
                        {saveMsg}
                    </div>
                )}
            </div>
        </div>
    );
}

// --- 时段配置 Tab ---
function TimePeriodTab() {
    const [config, setConfig] = useState(null);
    const [periods, setPeriods] = useState([]);
    const [saveMsg, setSaveMsg] = useState("");
    const [loading, setLoading] = useState(true);
    const [newName, setNewName] = useState("");
    const [newStart, setNewStart] = useState("");
    const [newEnd, setNewEnd] = useState("");

    useEffect(() => {
        loadConfig();
    }, []);

    async function loadConfig() {
        setLoading(true);
        try {
            const cfg = await callApi('get_time_period_config');
            if (cfg && !cfg.error) {
                setConfig(cfg);
                setPeriods(cfg["时段"] ? cfg["时段"].map((p, i) => ({ ...p, _id: i })) : []);
            } else {
                setSaveMsg("加载配置失败: " + (cfg?.error || "未知错误"));
            }
        } catch (e) {
            setSaveMsg("加载配置失败: " + (e.message || e));
        }
        setLoading(false);
    }

    /** 归一化时间字符串中的冒号（全角 → 半角） */
    function normColon(value) {
        return value.replace(/：/g, ":");
    }

    function updatePeriod(index, field, value) {
        // 时间字段自动归一化冒号
        const normalized = (field === "start" || field === "end") ? normColon(value) : value;
        setPeriods(prev => prev.map((p, i) => i === index ? { ...p, [field]: normalized } : p));
        setSaveMsg("");
    }

    function removePeriod(index) {
        setPeriods(prev => prev.filter((_, i) => i !== index));
        setSaveMsg("");
    }

    function addPeriod() {
        const name = newName.trim();
        // 归一化冒号
        const start = normColon(newStart.trim());
        const end = normColon(newEnd.trim());
        if (!name || !start || !end) return;
        // 验证时间格式 HH:MM（半角冒号）
        const timeRe = /^\d{1,2}:\d{2}$/;
        if (!timeRe.test(start) || !timeRe.test(end)) {
            setSaveMsg("❌ 时间格式应为 HH:MM（如 06:00）");
            return;
        }
        // 验证开始 < 结束
        const startMin = parseTime(start);
        const endMin = parseTime(end);
        if (startMin < 0 || endMin < 0 || startMin >= endMin) {
            setSaveMsg("❌ 开始时间必须小于结束时间");
            return;
        }
        setPeriods(prev => [...prev, { name, start, end, _id: Date.now() }]);
        setNewName("");
        setNewStart("");
        setNewEnd("");
        setSaveMsg("");
    }

    async function handleSave() {
        setSaveMsg("");
        const toSave = {
            "时段": periods.map(({ name, start, end }) => ({ name, start, end }))
        };
        const result = await callApi('save_time_period_config', toSave);
        if (result === "ok") {
            setConfig(toSave);
            setSaveMsg("✅ 配置已保存");
            setTimeout(() => setSaveMsg(""), 3000);
        } else {
            setSaveMsg("❌ " + result);
        }
    }

    if (loading) {
        return <div className="card"><div style={{textAlign:"center", padding:40, color:"var(--text-secondary)"}}>加载中...</div></div>;
    }

    return (
        <div>
            {/* 分类逻辑流程图 */}
            <div className="card">
                <div className="card-title">📐 时间分类逻辑</div>
                <div className="logic-flow">
                    <div className="flow-row">
                        <span style={{fontWeight:600}}>⏰ 时间列</span>
                        <span style={{color:"var(--text-secondary)"}}>（HH:MM / HH:MM:SS 格式）</span>
                    </div>
                    <div className="flow-indent">
                        <div className="flow-row">
                            <span className="flow-arrow">↓</span>
                            <span>解析为分钟数（0 ~ 1439）</span>
                        </div>
                        <div className="flow-row">
                            <span className="flow-arrow">↓</span>
                            <span>按配置顺序依次匹配时段</span>
                        </div>
                        <div className="flow-row">
                            <span className="flow-arrow">↓</span>
                            <span>start ≤ 分钟数 &lt; end → 命中</span>
                        </div>
                    </div>
                    <div className="flow-row">
                        <span className="flow-arrow" style={{marginLeft:20}}>→</span>
                        <span className="flow-result">写入「时段」列</span>
                        <span style={{color:"var(--text-secondary)", fontSize:12}}>（明细表最右侧，备注2 之后）</span>
                    </div>
                    <div style={{borderTop:"1px solid var(--border)", margin:"10px 0"}}></div>
                    <div className="flow-row">
                        <span style={{color:"var(--text-secondary)"}}>未命中任何时段 → </span>
                        <span className="flow-label flow-label-exclude">未知</span>
                    </div>
                </div>
            </div>

            {/* 时段列表编辑 */}
            <div className="card">
                <div className="card-title">
                    ⏰ 时段配置
                    <span style={{fontSize:12, color:"var(--text-secondary)", fontWeight:400, marginLeft:8}}>
                        按数组顺序匹配（第一个命中即返回）
                    </span>
                </div>

                {periods.length === 0 ? (
                    <div style={{padding: 20, textAlign: "center", color: "var(--text-secondary)", fontSize: 13}}>
                        暂无时段配置，请添加
                    </div>
                ) : (
                    <div style={{marginBottom: 12}}>
                        {/* 表头 */}
                        <div className="time-period-row time-period-header">
                            <span style={{flex: 1, fontSize: 12, color: "var(--text-secondary)", fontWeight: 500}}>时段名称</span>
                            <span style={{width: 80, fontSize: 12, color: "var(--text-secondary)", fontWeight: 500, textAlign: "center"}}>开始</span>
                            <span style={{width: 30, textAlign: "center", color: "var(--text-secondary)"}}>~</span>
                            <span style={{width: 80, fontSize: 12, color: "var(--text-secondary)", fontWeight: 500, textAlign: "center"}}>结束</span>
                            <span style={{width: 50}}></span>
                        </div>
                        {periods.map((p, i) => (
                            <div className="time-period-row" key={p._id}>
                                <input
                                    className="form-input"
                                    style={{flex: 1}}
                                    value={p.name}
                                    onChange={e => updatePeriod(i, "name", e.target.value)}
                                    placeholder="时段名称"
                                />
                                <input
                                    className="form-input time-input"
                                    value={p.start}
                                    onChange={e => updatePeriod(i, "start", e.target.value)}
                                    placeholder="HH:MM"
                                />
                                <span style={{width: 30, textAlign: "center", color: "var(--text-secondary)"}}>~</span>
                                <input
                                    className="form-input time-input"
                                    value={p.end}
                                    onChange={e => updatePeriod(i, "end", e.target.value)}
                                    placeholder="HH:MM"
                                />
                                <button
                                    className="btn btn-danger"
                                    style={{width: 50}}
                                    onClick={() => removePeriod(i)}
                                    title="删除此时段"
                                >×</button>
                            </div>
                        ))}
                    </div>
                )}

                {/* 添加新时段 */}
                <div style={{borderTop: "1px solid var(--border)", paddingTop: 12}}>
                    <div style={{fontSize: 12, color: "var(--text-secondary)", marginBottom: 8}}>+ 添加新时段</div>
                    <div className="time-period-row">
                        <input
                            className="form-input"
                            style={{flex: 1}}
                            value={newName}
                            onChange={e => setNewName(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter") addPeriod(); }}
                            placeholder="时段名称"
                        />
                        <input
                            className="form-input time-input"
                            value={newStart}
                            onChange={e => setNewStart(normColon(e.target.value))}
                            placeholder="HH:MM"
                        />
                        <span style={{width: 30, textAlign: "center", color: "var(--text-secondary)"}}>~</span>
                        <input
                            className="form-input time-input"
                            value={newEnd}
                            onChange={e => setNewEnd(normColon(e.target.value))}
                            placeholder="HH:MM"
                        />
                        <button className="btn btn-primary btn-sm" style={{width: 50}} onClick={addPeriod}>
                            + 添加
                        </button>
                    </div>
                </div>
            </div>

            {/* 保存 */}
            <div style={{textAlign: "center", marginBottom: 16}}>
                <button className="btn btn-primary btn-lg" onClick={handleSave}>
                    💾 保存配置
                </button>
                {saveMsg && (
                    <div style={{
                        marginTop: 8,
                        fontSize: 13,
                        color: saveMsg.startsWith("✅") ? "var(--success)" : "var(--danger)"
                    }}>
                        {saveMsg}
                    </div>
                )}
            </div>
        </div>
    );
}

// ========== 根组件 ==========
function App() {
    const [activeTab, setActiveTab] = useState("batch");

    return (
        <>
            <div className="header">
                <h1>💳 财付通交易流水处理工具</h1>
                <span className="version">v4.0</span>
            </div>
            <div className="tabs">
                <div className={`tab ${activeTab === "batch" ? "active" : ""}`} onClick={() => setActiveTab("batch")}>
                    单批次清洗
                </div>
                <div className={`tab ${activeTab === "merge" ? "active" : ""}`} onClick={() => setActiveTab("merge")}>
                    多批次合并
                </div>
                <div className={`tab ${activeTab === "parking" ? "active" : ""}`} onClick={() => setActiveTab("parking")}>
                    ⚙️ 停车配置
                </div>
                <div className={`tab ${activeTab === "timeperiod" ? "active" : ""}`} onClick={() => setActiveTab("timeperiod")}>
                    ⏰ 时段配置
                </div>
            </div>
            <div className="main">
                {activeTab === "batch" ? <BatchTab />
                 : activeTab === "merge" ? <MergeTab />
                 : activeTab === "parking" ? <ParkingConfigTab />
                 : <TimePeriodTab />}
            </div>
        </>
    );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
