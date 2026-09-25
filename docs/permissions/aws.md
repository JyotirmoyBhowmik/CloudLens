# Amazon Web Services (AWS) Permission Reference

> **Provider**: Amazon Web Services (AWS)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Owning Connector**: `connectors/aws` (`Prompt 17`)

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Cross-Account IAM Role + External ID** | STS `AssumeRole` with unique external ID (recommended) | **Primary** |
| **OIDC Web Identity Federation** | Kubernetes EKS service account or GitHub Actions OIDC | **Supported** |
| **IAM Identity Center** | Federated short-lived identity assertions | **Supported** |
| **Long-Lived Access Keys** | IAM User access key/secret key with mandatory 90-day rotation | **Restricted** |
| **Root Credentials** | AWS account root user credentials | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Group | AWS Managed Policy / Actions | Required Scope | Capability Flag |
|:---|:---|:---|:---:|
| **Hierarchy Discovery** | `organizations:Describe*`, `organizations:List*` | Organization Management / Delegation | `C-01` |
| **Resource Inventory** | `resource-explorer-2:Search`, `tag:GetResources` | AWS Account / Aggregator Region | `C-02` |
| **Cost Ingestion** | `ce:GetCostAndUsage`, `s3:GetObject` on CUR bucket | Management Account | `C-03` |
| **Usage Metrics** | `cloudwatch:GetMetricData`, `cloudwatch:ListMetrics` | Account | `C-04` |
| **Pricing Discovery** | `pricing:GetProducts`, `pricing:DescribeServices` | Global (`us-east-1`) | `C-11` |
| **Quota & Limits** | `servicequotas:GetServiceQuota`, `servicequotas:List*` | Account | `C-18` |
