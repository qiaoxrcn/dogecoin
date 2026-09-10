# k3d-c4 Dogecoin reorg 测试节点

此部署运行 regtest + testnet 格式模式，使用已经验证的 Docker 镜像摘要。

- Context：`k3d-c4`
- Namespace：`default`
- StatefulSet / Pod：`dogecoin-testnet` / `dogecoin-testnet-0`
- 同 namespace 的 RPC 地址：`http://dogecoin-testnet:44555`
- 跨 namespace 的 RPC 地址：`http://dogecoin-testnet.default.svc.cluster.local:44555`
- P2P：`dogecoin-testnet:44556`
- PVC：`data-dogecoin-testnet-0`，5 GiB，`local-path`
- 数据路径：`/data/regtest-testnet/`
- RPC 凭据：Secret `dogecoin-testnet-rpc` 的 `username` 和 `password`

## 部署与检查

部署前需要在 `default` 中创建包含 `username` 和 `password` 的
`dogecoin-testnet-rpc` Secret；凭据不写入 Git。已安装的集群直接复用现有 Secret。

```bash
kubectl --context k3d-c4 apply -f deploy/k3d-c4/dogecoin-testnet.yaml
kubectl --context k3d-c4 -n default rollout status statefulset/dogecoin-testnet
kubectl --context k3d-c4 -n default get pods,svc,pvc -l app=dogecoin-testnet
```

浏览器 Pod 可通过 `secretKeyRef` 引用同 namespace 下该 Secret 的凭据，
使用 HTTP Basic Auth 访问 RPC。其他 namespace 的客户端需要在自己的
namespace 中配置凭据，并使用上面的完整服务域名。

在自己的终端读取密码：

```bash
kubectl --context k3d-c4 -n default get secret dogecoin-testnet-rpc \
  -o jsonpath='{.data.password}' | base64 -d
```

## 挖矿与回退

先在 Bash 终端定义快捷函数，它会读取 Pod 中的 RPC 凭据：

```bash
rpc() {
  kubectl --context k3d-c4 -n default exec dogecoin-testnet-0 -- sh -c '
    exec dogecoin-cli -regtest -regtesttestnet -datadir=/data -rpcport=44555 \
      -rpcuser="$DOGECOIN_RPC_USER" -rpcpassword="$DOGECOIN_RPC_PASSWORD" "$@"
  ' sh "$@"
}
rpc getblockchaininfo
```

### 挖矿到指定地址

```bash
MINING_ADDRESS=nq5qTGSppHq2uAawXqQcqCtr5sdf9pyuHX

# 生成 1 个区块，coinbase 奖励直接支付给指定地址。
rpc generatetoaddress 1 "$MINING_ADDRESS"

# 查询当前高度。
rpc getblockcount
```

目标地址不需要导入节点钱包，节点也不需要持有该地址的私钥。
`generatetoaddress` 返回新生成区块的哈希数组；奖励需要满足 coinbase
成熟条件后才能花费。此私有 regtest 链的 coinbase 成熟参数是 60 块。

如果希望奖励发给节点自己的钱包，可以改用：

```bash
rpc generate 1
```

### 单节点触发回退并生成替代分支

以下操作要求当前链至少已有 1 个非创世区块。先保存旧链头哈希，
这样后续可以检查旧区块状态或解除无效标记：

```bash
OLD_TIP="$(rpc getbestblockhash)"

# 一个 RPC 调用：使旧链头区块退出主链。
rpc invalidateblock "$OLD_TIP"
rpc getblockcount

# 等浏览器处理回退后，生成 2 个新区块，奖励仍支付到指定地址。
rpc generatetoaddress 2 "$MINING_ADDRESS"

# 查看旧区块，退出主链的区块 confirmations 为 -1。
rpc getblock "$OLD_TIP"
```

例如原高度为 100，这个流程通常是 `100 → 99 → 101`。如果节点已经知道
其他有效分支，`invalidateblock` 会重新选择最佳有效链，而不一定停在父区块。

要回退最近 N 块，对高度 `当前高度 - N + 1` 的区块调用 `invalidateblock`。
例如高度为 100 时，先 `rpc getblockhash 98`，再将返回的哈希传给
`invalidateblock`，即可使第 98、99、100 块退出当前主链。

如果需要撤销无效标记，单独执行：

```bash
rpc reconsiderblock "$OLD_TIP"
```

`reconsiderblock` 让相关分支重新参与最佳链选择；如果替代分支累计工作量更高，
它不保证切回旧分支。`invalidateblock` 是当前节点的本地管理操作，不会要求
其他节点也将同一个区块标记为无效。

## 宿主机访问

集群外的开发机可以临时转发 RPC。以下命令监听宿主机所有 IPv4/IPv6 网卡：

```bash
kubectl --context k3d-c4 -n default \
  port-forward --address=0.0.0.0,:: svc/dogecoin-testnet 44555:44555
```

保持该命令运行。宿主机可使用 `http://127.0.0.1:44555`，能访问宿主机的其他
客户端可使用 `http://<宿主机IP>:44555`，认证凭据相同。端口转发进程退出或
目标 Pod 重建后需要重新执行。只需本机访问时，将 `--address` 改为 `127.0.0.1`。

## 通过 HTTP JSON-RPC 挖矿和 reorg

以下 Bash 示例需要 `curl` 和 `jq`。在配置了 kubectl 的宿主机上，先开启
上面的端口转发，再设置连接参数；集群内客户端把 `RPC_URL` 改为服务地址，
并从自己的 Secret 或配置中读取凭据：

```bash
export RPC_URL=http://127.0.0.1:44555
export RPC_USER="$(kubectl --context k3d-c4 -n default get secret dogecoin-testnet-rpc -o jsonpath='{.data.username}' | base64 -d)"
export RPC_PASSWORD="$(kubectl --context k3d-c4 -n default get secret dogecoin-testnet-rpc -o jsonpath='{.data.password}' | base64 -d)"

rpc_http() {
  local request
  request="$(jq -cn --arg method "$1" --argjson params "${2:-[]}" \
    '{jsonrpc:"1.0",id:"reorg-test",method:$method,params:$params}')" || return
  curl --silent --show-error --max-time 120 "$RPC_URL" \
    --user "$RPC_USER:$RPC_PASSWORD" \
    --header 'Content-Type: application/json' \
    --data-binary "$request"
}

# 挖 1 块，奖励给指定地址。
rpc_http generatetoaddress '[1,"nq5qTGSppHq2uAawXqQcqCtr5sdf9pyuHX"]'

# 保存链头，再通过一个 HTTP 请求触发回退。
OLD_TIP="$(rpc_http getbestblockhash | jq -er '.result')"
rpc_http invalidateblock "$(jq -cn --arg hash "$OLD_TIP" '[$hash]')"

# 等浏览器处理回退后，通过 HTTP 请求生成替代分支。
rpc_http generatetoaddress '[2,"nq5qTGSppHq2uAawXqQcqCtr5sdf9pyuHX"]'
rpc_http getblockcount

# 如需解除旧区块的无效标记，可单独调用：
# rpc_http reconsiderblock "$(jq -cn --arg hash "$OLD_TIP" '[$hash]')"
```

每次请求都应检查返回 JSON 的 `error` 是否为 `null`。`invalidateblock` 和
`reconsiderblock` 成功时 `result` 为 `null`；挖矿成功时 `result` 为区块哈希数组。
若挖矿请求超时，先查询链头或高度确认执行结果，不要直接重复发送，以免多挖区块。

Pod 重建会复用 PVC；不要为重置测试随意删除 PVC，它包含区块链和钱包数据。
