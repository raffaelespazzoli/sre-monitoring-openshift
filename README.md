# SRE Monitoring for OCP

## Pormetheus and Grafana deployment

The following are the steps to deploy a parallel grafan/prometheus/alertmanager stack to what comes up with ServiceMesh

### Preparation

```shell
export istio_cp_namespace=istio-system
export deploy_namespace=sre-monitoring
export istio_cp_name=basic-install

oc new-project ${deploy_namespace}
```

### Deploy Prometheus Operator

```shell
cat prometheus-operator.yaml | envsubst | oc apply -f - -n ${deploy_namespace}
```

### Deploy Grafana Operator

```shell
oc apply -f ./grafana-operator/crds
oc apply -f ./grafana-operator/manifests -n ${deploy_namespace}
cat ./grafana-operator/cluster_role_binding_grafana_operator.yaml | envsubst | oc apply -f -
```

### Deploy Prometheus

```shell
export cert_chain_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["cert-chain.pem"]')
export key_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["key.pem"]')
export root_cert_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["root-cert.pem"]')
oc get ServiceMeshMemberRoll/default -n istio-system -o json | jq -r .spec > /tmp/members.json
helm template prometheus-sre --namespace ${deploy_namespace}  -f /tmp/members.json --set istio_control_plane_name=${istio_cp_name} --set istio_control_plane_namespace=${istio_cp_namespace} --set istio_cert.cert_chain=${cert_chain_pem} --set istio_cert.key=${key_pem} --set istio_cert.root_cert=${root_cert_pem} | oc apply -f -
#wait a few minutes
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-name=default" }]' -n ${deploy_namespace}

oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-namespace='${istio_cp_namespace}'" }]' -n ${deploy_namespace}

oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/volumeMounts/-", "value":  { "name": "istio-certs", "mountPath": "/etc/istio-certs" }  }]' -n ${deploy_namespace}
```

### Deploy Grafana with openshift-monitoring and sre prometheus datasources

```shell
helm template grafana-sre --namespace ${deploy_namespace} --set prometheus_datasource.openshift_monitoring.password=$(oc get secret grafana-datasources -n openshift-monitoring -o jsonpath="{.data['prometheus\.yaml']}" | base64 -d | jq -r '.datasources[0].basicAuthPassword') | oc apply -f -
```

## Error Budget Demo

The following are the steps to run the error budget demo

### Deploy bookinfo and generate load

Follow instructions [here] to deploy OCP Service Mesh and bookinfo, the example app.
Follow the steps below to deploy locust, a load generator

```shell
oc new-project locust
export istio_gateway_url=$(oc get route istio-ingressgateway -n istio-system -o jsonpath='{.spec.host}')
oc create configmap locust-tasks --from-file=tasks.py=./locust/locustfile.py -n locust
helm install stable/locust --namespace locust --set master.config.target-host=http://$istio_gateway_url -f ./locust/values.yaml --name-template locust
oc expose service locust-master-svc --port 8089 --name locust -n locust
```

### Start Swarming

```shell
export locust_url=$(oc get route -n locust locust -o jsonpath='{.spec.host}')
curl -X POST -H "Content-Type: application/x-www-form-urlencoded" -d "locust_count=2&hatch_rate=2" http://${locust_url}/swarm
```

### Fault injection

```shell
oc apply -f failure-injection.yaml -n bookinfo
```

### create SLO-based alerts

```shell
helm template sre-service-monitor-istio --namespace $deploy_namespace{} --set slo_percent=95 --set prometheus=sre-prometheus | oc apply -f -
```

## Notes

[chao-smesh](https://github.com/pingcap/chaos-mesh)

### Monitoring the master-api

```shell
helm template sre-service-monitor --namespace openshift-monitoring --values ./master-api-values.yaml | oc apply -f -
```

### Useful PromQL

error rate:

sum(rate(istio_requests_total{destination_service_namespace="bookinfo",destination_service="details.bookinfo.svc.cluster.local",response_code!~"5.*"}[5m]))/sum(rate(istio_requests_total{destination_service_namespace="bookinfo",destination_service="details.bookinfo.svc.cluster.local"}[5m]))

sum(increase(istio_requests_total{connection_security_policy!="none",destination_service="$virtual_service",response_code!~"5.*"}[$time_interval]))/sum(increase(istio_requests_total{connection_security_policy!="none",destination_service="$virtual_service"}[$time_interval]))  

sum(increase(istio_request_duration_seconds_bucket{connection_security_policy!="none",destination_service="$virtual_service",response_code!~"5.*",le="$latency"}[$time_interval]))/sum(increase(istio_request_duration_seconds_bucket{connection_security_policy!="none",destination_service="$virtual_service",le="+Inf"}[$time_interval]))

istio_request_duration_seconds_bucket{connection_security_policy!="none",destination_service="$virtual_service",response_code!~"5.*"}
