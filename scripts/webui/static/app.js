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
                    <div className="card-title">📋 处理日志</div>
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
        const path = await callApi('select_file', "Excel files (*.xlsx)|*.xlsx");
        if (!path) return;
        // 确保以 .xlsx 结尾
        setOutput(path.endsWith('.xlsx') ? path : path + '.xlsx');
    };

    const handleStart = async () => {
        if (inputFiles.length === 0 || !output) return;
        const filesStr = inputFiles.map(f => f.path).join("|");
        setRunning(true);
        setStatus({ status: "running", total: 0, current: 0, success: 0, fail: 0, skipped: 0, logs: [], result: {} });
        const result = await callApi('start_merge_process', filesStr, output);
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
                    <span className="form-label">输出文件</span>
                    <input className="form-input" value={output} readOnly placeholder="选择输出位置..." />
                    <button className="btn btn-secondary" onClick={handleSelectOutput} disabled={running}>选择</button>
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
                    <div className="card-title">📋 合并进度</div>
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
            </div>
            <div className="main">
                {activeTab === "batch" ? <BatchTab /> : <MergeTab />}
            </div>
        </>
    );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
