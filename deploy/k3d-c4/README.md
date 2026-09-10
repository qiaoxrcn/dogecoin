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

```bash
rpc() {
  kubectl --context k3d-c4 -n default exec dogecoin-testnet-0 -- sh -c '
    exec dogecoin-cli -regtest -regtesttestnet -datadir=/data -rpcport=44555 \
      -rpcuser="$DOGECOIN_RPC_USER" -rpcpassword="$DOGECOIN_RPC_PASSWORD" "$@"
  ' sh "$@"
}
rpc getblockchaininfo
rpc generate 65
rpc invalidateblock "$(rpc getbestblockhash)"
rpc generate 2
```

这些方法也可以通过服务地址发送 HTTP JSON-RPC 请求调用。
从集群外的开发机访问时，可临时转发：

```bash
kubectl --context k3d-c4 -n default port-forward svc/dogecoin-testnet 44555:44555
```

然后使用 `http://127.0.0.1:44555` 和相同的 RPC 凭据。
Pod 重建会复用 PVC；不要为重置测试随意删除 PVC，它包含区块链和钱包数据。
