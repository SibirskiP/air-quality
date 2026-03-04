# Minikube deploy

## Build images in Minikube Docker daemon

```bash
minikube start
minikube docker-env | Invoke-Expression

docker build -f services/api/Dockerfile -t airq-api:latest .
docker build -f services/sensor-gateway/Dockerfile -t airq-sensor-gateway:latest .
docker build -f services/collector-openmeteo/Dockerfile -t airq-collector-openmeteo:latest .
docker build -f services/collector-fhmz/Dockerfile -t airq-collector-fhmz:latest .
docker build -f services/processor/Dockerfile -t airq-processor:latest .
```

## Apply manifests

```bash
kubectl apply -f infra/k8s/airq-stack.yaml
kubectl -n airq get pods
kubectl -n airq port-forward svc/api 8000:8000
```