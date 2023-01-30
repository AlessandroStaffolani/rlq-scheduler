# open-ebs

Volume and storage class operator

## Install:

Install the operator

```
helm repo add openebs https://openebs.github.io/charts
helm repo update
helm install openebs --namespace openebs openebs/openebs --create-namespace
```

Install a jiva volume policy and a storage class

```
kubectl apply -f storage-class-jiva.yaml
```


## Optional test

```
kubectl apply -f test-deployment.yaml
```