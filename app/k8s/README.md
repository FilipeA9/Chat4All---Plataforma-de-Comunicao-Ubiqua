# Kubernetes Deployment Resources

This directory contains Kubernetes manifests for deploying Chat4All in production.

## Directory Structure

```
k8s/
├── cronjobs/
│   └── upload-gc.yaml          # Upload garbage collector CronJob (T095)
├── deployments/
│   ├── api-deployment.yaml     # FastAPI application deployment
│   └── worker-deployment.yaml  # Background worker deployments
├── services/
│   └── api-service.yaml        # API LoadBalancer service
├── configmaps/
│   └── app-config.yaml         # Application configuration
├── secrets/
│   └── app-secrets.yaml        # Sensitive configuration (not committed)
├── ingress/
│   └── api-ingress.yaml        # Ingress for external access
└── hpa/
    ├── api-hpa.yaml            # HorizontalPodAutoscaler for API
    └── worker-hpa.yaml         # HorizontalPodAutoscaler for workers
```

## Prerequisites

1. **Kubernetes Cluster**: 1.28+ with autoscaling enabled
2. **kubectl**: Configured to access your cluster
3. **Namespace**: Create `chat4all` namespace
4. **Storage Classes**: Persistent volumes for PostgreSQL, Redis, MinIO
5. **Ingress Controller**: NGINX or Traefik for external access
6. **Cert Manager**: For TLS certificate management (optional but recommended)

## Quick Start

### 1. Create Namespace

```bash
kubectl create namespace chat4all
```

### 2. Create Secrets

**⚠️ IMPORTANT**: Never commit secrets to version control!

```bash
# Create database secret
kubectl create secret generic chat4all-secrets \
  --from-literal=database-url="postgresql://user:password@postgres:5432/chat4all" \
  --from-literal=jwt-secret-key="your-secret-key" \
  --from-literal=minio-access-key="your-access-key" \
  --from-literal=minio-secret-key="your-secret-key" \
  --from-literal=redis-password="your-redis-password" \
  --namespace=chat4all
```

### 3. Apply ConfigMaps

```bash
kubectl apply -f k8s/configmaps/
```

### 4. Deploy Infrastructure (PostgreSQL, Redis, Kafka, MinIO)

Use Helm charts or operators for production infrastructure:

```bash
# PostgreSQL with Patroni
helm install postgres bitnami/postgresql-ha --namespace chat4all

# Redis
helm install redis bitnami/redis --namespace chat4all

# Kafka
helm install kafka bitnami/kafka --namespace chat4all

# MinIO
helm install minio bitnami/minio --namespace chat4all
```

### 5. Deploy Application

```bash
# Deploy API and workers
kubectl apply -f k8s/deployments/

# Deploy services
kubectl apply -f k8s/services/

# Deploy HPA (autoscaling)
kubectl apply -f k8s/hpa/

# Deploy Ingress
kubectl apply -f k8s/ingress/

# Deploy CronJobs
kubectl apply -f k8s/cronjobs/
```

### 6. Verify Deployment

```bash
# Check all resources
kubectl get all -n chat4all

# Check pod status
kubectl get pods -n chat4all

# Check HPA status
kubectl get hpa -n chat4all

# Check CronJob
kubectl get cronjobs -n chat4all

# View logs
kubectl logs -f deployment/api -n chat4all
```

## CronJobs

### Upload Garbage Collector (T095)

**Purpose**: Clean up abandoned file uploads older than 24 hours.

**Schedule**: Daily at 2 AM UTC (`0 2 * * *`)

**Manifest**: `k8s/cronjobs/upload-gc.yaml`

**Configuration**:
- `GC_RETENTION_HOURS`: How old uploads must be before deletion (default: 24)
- `GC_BATCH_SIZE`: Number of uploads to process per batch (default: 100)

**Monitoring**:
```bash
# View CronJob status
kubectl get cronjob upload-garbage-collector -n chat4all

# View job history
kubectl get jobs -n chat4all -l component=upload-gc

# View logs from last run
kubectl logs -n chat4all -l component=upload-gc --tail=100

# Manually trigger job (for testing)
kubectl create job --from=cronjob/upload-garbage-collector upload-gc-manual -n chat4all
```

**Metrics**:
- `uploads_cleaned_total`: Counter of cleaned uploads
- `cleanup_duration_seconds`: Histogram of cleanup duration

## Horizontal Pod Autoscaling (HPA)

### API HPA

**Target**: 70% CPU utilization
**Min Replicas**: 3
**Max Replicas**: 10
**Scale Down Stabilization**: 300s (5 minutes)

### Worker HPA

**Target**: 70% CPU utilization
**Min Replicas**: 5
**Max Replicas**: 20

## Health Checks

All deployments include:

**Liveness Probe**: `GET /health`
- Checks if application is running
- Restarts pod if unhealthy

**Readiness Probe**: `GET /ready`
- Checks if application can serve traffic
- Removes pod from service if not ready

## Resource Limits

### API Pods
- **Requests**: CPU 500m, Memory 512Mi
- **Limits**: CPU 2000m, Memory 2Gi

### Worker Pods
- **Requests**: CPU 250m, Memory 256Mi
- **Limits**: CPU 1000m, Memory 1Gi

### CronJob Pods (Upload GC)
- **Requests**: CPU 100m, Memory 256Mi
- **Limits**: CPU 500m, Memory 512Mi

## Security

### Service Account

Custom service account `chat4all-worker` with minimal permissions:
- Read ConfigMaps and Secrets
- Create Events for monitoring

### Security Context

All pods run as non-root user (UID 1000):
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
```

### Network Policies

Consider implementing Network Policies to restrict traffic:
- API can talk to PostgreSQL, Redis, Kafka, MinIO
- Workers can talk to PostgreSQL, Redis, Kafka, MinIO
- CronJobs can talk to PostgreSQL, MinIO

## Monitoring

### Prometheus Integration

All pods expose metrics on `/metrics`:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8000"
  prometheus.io/path: "/metrics"
```

### Grafana Dashboards

Import dashboards from `observability/`:
- `api_health.json`: API latency, throughput, errors
- `message_pipeline.json`: Kafka lag, worker throughput
- `database_performance.json`: Query latency, connection pool

## Troubleshooting

### CronJob not running

```bash
# Check CronJob configuration
kubectl describe cronjob upload-garbage-collector -n chat4all

# Check if job was created
kubectl get jobs -n chat4all -l component=upload-gc

# Check events
kubectl get events -n chat4all --sort-by='.lastTimestamp'
```

### Pod stuck in Pending

```bash
# Check pod events
kubectl describe pod <pod-name> -n chat4all

# Common issues:
# - Insufficient resources
# - Node selector mismatch
# - Persistent volume not available
```

### High memory usage

```bash
# Check current resource usage
kubectl top pods -n chat4all

# If OOMKilled, increase memory limits in deployment
```

### Database connection errors

```bash
# Verify database secret
kubectl get secret chat4all-secrets -n chat4all -o yaml

# Check database connectivity from pod
kubectl exec -it <pod-name> -n chat4all -- psql "$DATABASE_URL" -c "SELECT 1"
```

## Production Checklist

- [ ] Namespace created with resource quotas
- [ ] Secrets created and verified (NOT committed to Git)
- [ ] Infrastructure deployed (PostgreSQL HA, Redis Sentinel, Kafka 3-broker cluster)
- [ ] Persistent volumes configured with backup strategy
- [ ] Application deployed with min 3 API replicas
- [ ] HPA configured and tested
- [ ] Ingress configured with TLS (Let's Encrypt or org CA)
- [ ] Network policies applied
- [ ] Prometheus scraping configured
- [ ] Grafana dashboards imported
- [ ] Alertmanager rules configured
- [ ] Log aggregation configured (ELK/Loki)
- [ ] Backup jobs scheduled
- [ ] Disaster recovery plan documented
- [ ] Load testing completed
- [ ] Chaos engineering experiments run

## Rolling Updates

```bash
# Update image version
kubectl set image deployment/api api=chat4all/api:v2.1.0 -n chat4all

# Watch rollout status
kubectl rollout status deployment/api -n chat4all

# Rollback if needed
kubectl rollout undo deployment/api -n chat4all
```

## Scaling

```bash
# Manual scaling (if HPA disabled)
kubectl scale deployment/api --replicas=5 -n chat4all

# Check HPA status
kubectl get hpa -n chat4all

# Disable HPA (for manual scaling)
kubectl delete hpa api-hpa -n chat4all
```

## Cleanup

```bash
# Delete all resources (⚠️ DANGEROUS)
kubectl delete namespace chat4all

# Delete specific resources
kubectl delete -f k8s/cronjobs/
kubectl delete -f k8s/deployments/
```

## References

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Helm Charts](https://helm.sh/)
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)
- [Cert Manager](https://cert-manager.io/)
- [NGINX Ingress](https://kubernetes.github.io/ingress-nginx/)
