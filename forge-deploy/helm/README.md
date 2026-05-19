# helm/ — 交付模式 3（Helm Chart）

面向客户 **Kubernetes 私有化部署** 的 Chart。

## 计划包含的文件（待补）

```
helm/
├── Chart.yaml                 ← Chart 元信息
├── values.yaml                ← 默认值
├── values.example.yaml        ← 客户参考样例（全字段注释）
├── values.production.yaml     ← 生产参考
├── templates/
│   ├── _helpers.tpl
│   ├── deployment-admin.yaml
│   ├── deployment-server.yaml
│   ├── service-admin.yaml
│   ├── service-server.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── hpa-server.yaml
│   ├── pdb.yaml
│   ├── networkpolicy.yaml
│   ├── serviceaccount.yaml
│   ├── rbac.yaml
│   └── tests/
│       └── connection-test.yaml
└── crds/                      ← 如有自定义资源
```

## 必备生产实践

- 所有 Deployment 必配 `livenessProbe` + `readinessProbe` + `startupProbe`
- 所有容器必配 resources requests/limits
- `terminationGracePeriodSeconds` + `preStop` hook
- 关键工作负载 PDB
- forge-server HPA（按 CPU/内存，未来支持自定义指标）
- 默认开启 NetworkPolicy（egress/ingress 显式声明）
- 非 root 用户运行、只读根文件系统（可行时）
- 镜像 tag **明确版本**，禁止 latest

## 客户可变项（values）

字段名与 `../docker/.env.example` 和 `../gitlab/variables.md` **一一对应**。

详见 `../../../Project-Docs/04-Deployment/helm.md` 中的 values 顶层 key 清单。

## 凭证管理

- Chart 不持有凭证
- 客户通过 Kubernetes Secret / External Secrets Operator / Sealed Secrets 注入
- `values.example.yaml` 中凭证字段全部占位
