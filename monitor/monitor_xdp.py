#!/usr/bin/env python3
from bcc import BPF
import time
import sys

# ==========================================
# 1. XDP C Code (Runs directly on the NIC)
# ==========================================
bpf_text = """
#include <uapi/linux/bpf.h>
#include <uapi/linux/in.h>
#include <uapi/linux/if_ether.h>
#include <uapi/linux/ip.h>
#include <uapi/linux/tcp.h>

// Hash map to track total bytes and packets on Port 8000
BPF_ARRAY(pytorch_stats, u64, 2); // Index 0: Packets, Index 1: Bytes

int xdp_pytorch_interceptor(struct xdp_md *ctx) {
    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;

    // 1. Parse Ethernet Header
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end)
        return XDP_PASS;

    // Only inspect IPv4 packets
    if (eth->h_proto != bpf_htons(ETH_P_IP))
        return XDP_PASS;

    // 2. Parse IP Header
    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return XDP_PASS;

    // Only inspect TCP packets
    if (ip->protocol != IPPROTO_TCP)
        return XDP_PASS;

    // 3. Parse TCP Header
    // Note: ihl is in 32-bit words, so multiply by 4 to get bytes
    struct tcphdr *tcp = (void *)ip + ip->ihl * 4;
    if ((void *)(tcp + 1) > data_end)
        return XDP_PASS;

    // 4. Filter for PyTorch Federated Server (Port 8000)
    if (tcp->source == bpf_htons(8000) || tcp->dest == bpf_htons(8000)) {
        u32 pkt_idx = 0;
        u32 byte_idx = 1;
        
        u64 *pkt_cnt = pytorch_stats.lookup(&pkt_idx);
        u64 *byte_cnt = pytorch_stats.lookup(&byte_idx);
        
        if (pkt_cnt && byte_cnt) {
            __sync_fetch_and_add(pkt_cnt, 1);
            // Calculate payload size: Total IP length - IP header - TCP header
            u64 payload_len = bpf_ntohs(ip->tot_len) - (ip->ihl * 4) - (tcp->doff * 4);
            __sync_fetch_and_add(byte_cnt, payload_len);
        }
    }

    return XDP_PASS; 
}
"""

# ==========================================
# 2. Python User Space Loader
# ==========================================
if __name__ == "__main__":
    device = "wlp2s0"

    print(f"[+] Compiling XDP Program and attaching to {device}...")
    b = BPF(text=bpf_text)
    
    xdp_fn = b.load_func("xdp_pytorch_interceptor", BPF.XDP)
    
    try:
        b.attach_xdp(device, xdp_fn, 0)
        print(f"[✓] XDP attached successfully! Monitoring Port 8000 traffic at the hardware level.")
        print("[!] Press Ctrl+C to stop.\n")
        
        print(f"{'Time':<12} | {'Packets (NIC Level)':<20} | {'Payload Transferred (MB)':<25}")
        print("-" * 65)

        stats_map = b.get_table("pytorch_stats")
        
        while True:
            time.sleep(2) 
            
            packets = stats_map[stats_map.Key(0)].value
            bytes_transferred = stats_map[stats_map.Key(1)].value
            mb_transferred = bytes_transferred / (1024 * 1024)
            
            t = time.strftime('%H:%M:%S')
            print(f"{t:<12} | {packets:<20} | {mb_transferred:.2f} MB")

    except KeyboardInterrupt:
        print("\n[+] Detaching XDP from network interface...")
    finally:
        b.remove_xdp(device, 0)
        print("[✓] XDP detached. Goodbye!")