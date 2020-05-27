# SRE Monitoring for OCP

This set-up assumes that you have installed ServiceMesh in the istio-system namespace and deployed the bookinfo app in the bookinfo namespace.
Instructions to do so can be found [here](https://github.com/raffaelespazzoli/openshift-enablement-exam/tree/master/misc4.0/ServiceMesh)

## Prometheus and Grafana deployment

The following are the steps to deploy a parallel grafana/prometheus/alert-manager stack to what comes up with ServiceMesh

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
export cert_chain_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['cert-chain\.pem']}")
export key_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['key\.pem']}")
export root_cert_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['root-cert\.pem']}")

#Get a list of member to add a rolebinding for prometheus-istio-system in each control plane member namespace
echo "members: $(oc get ServiceMeshMemberRoll/default -n ${istio_cp_namespace} -o jsonpath="{.spec.members}" | sed s'/ /, /g')" > /tmp/members.yaml

helm template prometheus-sre --namespace ${deploy_namespace}  -f /tmp/members.yaml --set istio_control_plane.name=${istio_cp_name} --set istio_control_plane.namespace=${istio_cp_namespace} --set istio_cert.cert_chain=${cert_chain_pem} --set istio_cert.key=${key_pem} --set istio_cert.root_cert=${root_cert_pem} | oc apply -f -

#wait a few minutes
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-namespace='${istio_cp_namespace}'" }, {"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-name=default" }]' -n ${deploy_namespace}
```

### Deploy Grafana with openshift-monitoring and sre prometheus datasources

```shell
helm template grafana-sre --namespace ${deploy_namespace} --set prometheus_datasource.openshift_monitoring.password=$(oc extract secret/grafana-datasources -n openshift-monitoring --keys=prometheus.yaml --to=- | grep -zoP '"basicAuthPassword":\s*"\K[^\s,]*(?=\s*",)') | oc apply -f -
```

If you are running Git Bash on Windows without jq you can follow:

```shell
oc extract secret/grafana-datasources -n openshift-monitoring --keys=prometheus.yaml --to=-
#copy the value inside quotes for the key "basicAuthPassword" from terminal
export basic_auth_password="paste_here"
helm template grafana-sre --namespace ${deploy_namespace} --set prometheus_datasource.openshift_monitoring.password=${basic_auth_password} | oc apply -f -
```

## Error Budget Demo

The following are the steps to run the error budget demo

### Deploy bookinfo and generate load

Follow instructions [here](https://github.com/raffaelespazzoli/openshift-enablement-exam/tree/master/misc4.0/ServiceMesh) to deploy OCP Service Mesh and bookinfo, the example app.
Follow the steps below to deploy locust, a load generator

```shell
oc new-project locust
export istio_gateway_url=$(oc get route istio-ingressgateway -n istio-system -o jsonpath='{.spec.host}')
oc create configmap locust-tasks --from-file=tasks.py=./locust/locustfile.py -n locust
helm repo add stable https://kubernetes-charts.storage.googleapis.com
helm install stable/locust --namespace locust --set master.config.target-host=http://${istio_gateway_url} -f ./locust/values.yaml --name-template locust
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
helm template sre-service-monitor-istio --namespace ${deploy_namespace} --set slo_percent=95 --set latency=1 --set prometheus=sre-prometheus --set destination_service=details.bookinfo.svc.cluster.local --set metrics_labels.destination_service_namespace=bookinfo | oc apply -f -
```
