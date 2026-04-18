#!/bin/bash

echo "==========================================="
echo "  Real Distributed Test (Sanskar's Laptop) "
echo "==========================================="

sudo -v
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# --- NEW: Automatically Open Port 8000 ---
echo "[+] Punching hole in Linux firewall for Port 8000..."
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
# -----------------------------------------

chmod +x monitor/monitor_network.py
chmod +x monitor/monitor_gpu.py
chmod +x monitor/monitor_xdp.py # Added permission for the new script!

# Start XDP Monitor FIRST
echo "[+] Starting XDP Hardware Monitor..."
sudo python3 monitor/monitor_xdp.py > /dev/null 2>&1 &
XDP_PID=$!

echo "[+] Starting eBPF Kernel Monitors..."
sudo python3 monitor/monitor_network.py > /dev/null 2>&1 &
NET_PID=$!
sudo python3 monitor/monitor_gpu.py > /dev/null 2>&1 &
GPU_PID=$!

echo "[+] Waiting 8 seconds for BPF to compile..."
sleep 8

VENV_PYTHON="ebpf-env/bin/python3"

echo "[+] Starting Parameter Server (Port 8000)..."
$VENV_PYTHON src/server.py > /dev/null 2>&1 &
SERVER_PID=$!
sleep 3 

echo "[+] Starting Client 1..."
$VENV_PYTHON src/client.py 1 &
CLIENT1_PID=$!

echo "==========================================="
echo " KUNAL CAN NOW CONNECT TO CLIENT 2"
echo "==========================================="
echo ""
echo " ⚠️ DO NOT PRESS ENTER YET ⚠️"
echo " Wait for both your terminal AND Kunal's terminal to finish."

read -p " Press [ENTER] only when both clients are 100% finished... "

echo "[!] Stopping monitors and server gracefully..."
sudo kill -SIGINT $XDP_PID
sudo kill -SIGINT $NET_PID
sudo kill -SIGINT $GPU_PID
kill $SERVER_PID
sleep 5 

# --- NEW: Automatically Close Port 8000 (Security cleanup) ---
echo "[+] Restoring Linux firewall..."
sudo iptables -D INPUT -p tcp --dport 8000 -j ACCEPT
# -------------------------------------------------------------

LATEST_NET_CSV=$(ls -t monitor/network_trace_PHASE1_*.csv 2>/dev/null | head -1)
LATEST_GPU_CSV=$(ls -t monitor/gpu_trace_PHASE2_*.csv 2>/dev/null | head -1)

if [[ -n "$LATEST_NET_CSV" && -n "$LATEST_GPU_CSV" ]]; then
    echo "[+] Found CSVs! Generating Unified Timeline Dashboard..."
    $VENV_PYTHON monitor/plot_unified_timeline.py "$LATEST_NET_CSV" "$LATEST_GPU_CSV"
    echo "[✓] SUCCESS! Open phase3_unified_timeline.png"
fi