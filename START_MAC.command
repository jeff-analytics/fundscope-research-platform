#!/bin/bash
set -e
cd "$(dirname "$0")"
export FUNDSCOPE_ROLE="${FUNDSCOPE_ROLE:-maintainer}"
echo "FundScope v9.2.2"

stop_if_fundscope() {
  local port="$1"
  for pid in $(lsof -ti tcp:"$port" 2>/dev/null || true); do
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
    if echo "$cmd" | grep -Eqi 'FundScope|uvicorn main:app|vite'; then
      kill -9 "$pid" 2>/dev/null || true
    else
      echo "端口 $port 已被其他程序占用：$cmd"
      exit 2
    fi
  done
}

stop_if_fundscope 8000
stop_if_fundscope 5173

if ! command -v python3 >/dev/null 2>&1; then echo "未检测到 Python 3。"; exit 1; fi
if ! command -v node >/dev/null 2>&1; then echo "未检测到 Node.js 20 或更高版本。"; exit 1; fi

if [ ! -x "backend/.venv/bin/python" ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/python -m pip install --upgrade pip
  backend/.venv/bin/python -m pip install -r backend/requirements.txt
fi
if [ ! -d "frontend/node_modules" ]; then (cd frontend && npm install); fi

(cd backend && .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log) &
API_PID=$!
sleep 2
(cd frontend && npm run dev) &
WEB_PID=$!
sleep 2
command -v open >/dev/null 2>&1 && open http://127.0.0.1:5173
wait $API_PID $WEB_PID
