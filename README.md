# SRE Monitoring for OCP

https://github.com/pingcap/chaos-mesh

## Install the Grafana Operator

The first step is to install the Grafana operator to a namespace in your cluster.

There are two options for this procedure, automated via Ansible, or manually running kubectl/oc commands.

See the [grafana-operator documentation](https://github.com/integr8ly/grafana-operator/blob/master/documentation/deploy_grafana.md) for up-to-date info.

### Manual Procedure

```shell
#Clone the grafana-operator repository
git clone git@github.com:integr8ly/grafana-operator.git

#To create a namespace named "sre-monitoring" run:
oc create namespace sre-monitoring

#Create the custom resource definitions that the operator uses:
oc create -f deploy/crds

#Create the operator roles:
oc create -f deploy/roles -n sre-monitoring

#If you want to scan for dashboards in other namespaces you also need the cluster roles:
oc create -f deploy/cluster_roles

#To deploy the operator to that namespace you can use `deploy/operator.yaml`:
oc create -f deploy/operator.yaml -n sre-monitoring

#Check that the STATUS of the operator pod is Running:
oc get pods -n sre-monitoring
```

### Automated Procedure

```shell
git clone git@github.com:integr8ly/grafana-operator.git

cd grafana-operator/

ansible-playbook deploy/ansible/grafana-operator-cluster-resources.yaml \
  -e k8s_host=https://api.my-example-cluster.com:6443 \
  -e k8s_username=admin \
  -e k8s_password='password' \
  -e k8s_validate_certs=false \
  -e grafana_operator_namespace=sre-monitoring

ansible-playbook deploy/ansible/grafana-operator-namespace-resources.yaml \
  -e k8s_host=https://api.my-example-cluster.com:6443 \
  -e k8s_username=admin\
  -e k8s_password='password' \
  -e k8s_validate_certs=false \
  -e grafana_operator_namespace=sre-monitoring
```

## Deploy Grafana - connected to platform Prometheus

```shell
#Grab the current internal user password from the openshift-monitoring grafana instance
export INTERNAL_PASSWORD=$(oc get secret grafana-datasources -n openshift-monitoring -o jsonpath="{.data['prometheus\.yaml']}" | base64 -d | jq -r '.datasources[0].basicAuthPassword')

#Make the datasource use the internal user
helm template grafana-ocp --namespace sre-monitoring --set prometheus_datasource.password=$INTERNAL_PASSWORD | oc apply -f -
```

## Deploy Service Monitoring

```shell
helm template sre-service-monitor --namespace grafana-operator | oc apply -f -
```

## Monitoring the master-api

```shell
helm template sre-service-monitor --namespace openshift-monitoring --values ./master-api-values.yaml | oc apply -f -
```

## Deploy Grafana - connected to istio Prometheus


```shell
export ISTIO_PASSWORD=$(oc get secret htpasswd -n istio-system -o jsonpath='{.data.rawPassword}' | base64 -d)

#Make the datasource use the internal user
helm template grafana-ocp --namespace sre-monitoring --values ./istio-prometheus-values.yaml --set prometheus_datasource.password=$ISTIO_PASSWORD | oc apply -f -
```

## Deploy bookinfo and generate load

Follow instructions [here] to deploy OCP Service Mesh and bookinfo, the example app.
Follow the steps below to deploy locust, a load generator

```shell
oc new-project locust
export istio_gateway_url=$(oc get route istio-ingressgateway -n istio-system -o jsonpath='{.spec.host}')
oc create configmap locust-tasks --from-file=tasks.py=./locust/locustfile.py -n locust
helm repo add stable https://kubernetes-charts.storage.googleapis.com/
export locust_chart_version=$(helm search repo locust | grep locust | awk '{print $2}')
helm fetch stable/locust --version ${locust_chart_version}
helm template locust-${locust_chart_version}.tgz --namespace locust --set master.config.target-host=http://$istio_gateway_url -f ./locust/values.yaml --name-template locust | oc apply -f -
rm locust-${locust_chart_version}.tgz
oc expose service locust-master-svc --port 8089 --name locust -n locust
```

## Start Swarming

```shell
export locust_url=$(oc get route -n locust locust -o jsonpath='{.spec.host}')
curl -X POST -H "Content-Type: application/x-www-form-urlencoded" -d "locust_count=2&hatch_rate=2" http://${locust_url}/swarm
```

## Deploy Prometheus Operator

```shell
oc new-project sre-monitoring
oc apply -f prometheus-operator.yaml -n sre-monitoring
```

## Deploy Prometheus to watch Istio

```shell
```

## Deploy Prometheus Sre Prometheus

```shell
export token=$(oc get secret htpasswd -n istio-system -o jsonpath='{.data.rawPassword}' | base64 -d)
helm template prometheus-sre --namespace sre-monitoring --set prometheus.istio_endpoint.token=$token | oc apply -f -
```

## New Try for extensible istio monitoring

```shell
export istio_cp_namespace=istio-system
export deploy_namespace=sre-monitoring
oc new-project ${deploy_namespace}
oc patch ServiceMeshMemberRoll/default --type='json' -p='[{"op": "add", "path": "/spec/members/-", "value": "'${deploy_namespace}'" }]' -n ${istio_cp_namespace}
cat prometheus-operator.yaml | envsubst | oc apply -f - -n ${deploy_namespace}
export cert_chain_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["cert-chain.pem"]')
export key_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["key.pem"]')
export root_cert_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["root-cert.pem"]')
oc get ServiceMeshMemberRoll/default -n istio-system -o json | jq -r .spec | j2y > /tmp/members.yaml
helm template prometheus-sre --namespace ${deploy_namespace}  -f /tmp/members.yaml --set istio_control_plane_namespace=${istio_cp_namespace} --set istio_cert.cert_chain=${cert_chain_pem} --set istio_cert.key=${key_pem} --set istio_cert.root_cert=${root_cert_pem} | oc apply -f -
#wait a few minutes
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-name=default" }]' -n ${deploy_namespace}
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-namespace='${istio_cp_namespace}'" }]' -n ${deploy_namespace}
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/volumeMounts/-", "value":  { "name": "istio-certs", "mountPath": "/etc/istio-certs" }  }]' -n ${deploy_namespace}
```

## Deploy Grafana with openshift-monitoring and sre prometheus datasources

```shell
oc new-project sre-monitoring

export istio_cp_namespace=istio-system
export deploy_namespace=sre-monitoring
export istio_cp_name=mtls-install

#Note: you must have mesh-user role on istio-system namespace
oc create -f - <<EOF
apiVersion: maistra.io/v1
kind: ServiceMeshMember
metadata:
  name: default
  namespace: $deploy_namespace
spec:
  controlPlaneRef:
    name: $istio_cp_name
    namespace: $istio_cp_namespace
EOF

cat prometheus-operator.yaml | envsubst | oc apply -f - -n ${deploy_namespace}
#Check that the STATUS of the prometheus-operator pod is Running.
oc get pods -n sre-monitoring

#Check that the STATUS of the grafana-operator pod is Running.
#If the operator is not installed follow the instructions at the top of this document to do so
oc get pods -n sre-monitoring

export cert_chain_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["cert-chain.pem"]')
export key_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["key.pem"]')
export root_cert_pem=$(oc get secret -n istio-system istio.default -o json | jq -r '.data["root-cert.pem"]')
oc get ServiceMeshMemberRoll/default -n istio-system -o json | jq -r .spec > /tmp/members.yaml
helm template prometheus-sre --namespace ${deploy_namespace}  -f /tmp/members.yaml --set istio_control_plane_namespace=${istio_cp_namespace} --set istio_cert.cert_chain=${cert_chain_pem} --set istio_cert.key=${key_pem} --set istio_cert.root_cert=${root_cert_pem} | oc apply -f -
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-name=default" }]' -n ${deploy_namespace}
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-namespace='${istio_cp_namespace}'" }]' -n ${deploy_namespace}
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/volumeMounts/-", "value":  { "name": "istio-certs", "mountPath": "/etc/istio-certs" }  }]' -n ${deploy_namespace}

#Deploy Grafana
helm template grafana-sre --namespace sre-monitoring --set prometheus_datasource.openshift_monitoring.password=$(oc get secret grafana-datasources -n openshift-monitoring -o jsonpath="{.data['prometheus\.yaml']}" | base64 -d | jq -r '.datasources[0].basicAuthPassword') | oc apply -f -
```

error rate:

sum(rate(istio_requests_total{destination_service_namespace="bookinfo",destination_service="details.bookinfo.svc.cluster.local",response_code!~"5.*"}[5m]))/sum(rate(istio_requests_total{destination_service_namespace="bookinfo",destination_service="details.bookinfo.svc.cluster.local"}[5m]))


## Fault injection

```shell
oc apply -f failure-injection.yaml -n bookinfo
```
