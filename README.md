# SRE Monitoring for OCP

## Install Gafana Operator

```shell
oc new-project sre-monitoring
oc apply -f operator.yaml -n sre-monitoring
#fixes some operator's bug
oc scale deployment grafana-operator --replicas=0
#oc set image deployment/grafana-operator grafana-operator=quay.io/integreatly/grafana-operator:v3.0.0-beta
oc set image deployment/grafana-operator grafana-operator=quay.io/integreatly/grafana-operator:v1.4.0
oc scale deployment grafana-operator --replicas=1
```

## Deploy Grafana - connected to platform Prometheus

```shell
oc create sa platform-prometheus-reader -n sre-monitoring
oc adm policy add-cluster-role-to-user view -z platform-prometheus-reader -n sre-monitoring
export secret_name=$(oc get sa platform-prometheus-reader -o json | jq -r '.secrets[].name | select (.|contains("token"))')
export token=$(oc get secret $secret_name -o jsonpath='{.data.token}' | base64 -d)
helm template grafana-ocp --namespace sre-monitoring --set prometheus_datasource.token=$token | oc apply -f -
# fixes for current bugs of the grafana operator
oc annotate serviceaccount grafana-serviceaccount serviceaccounts.openshift.io/oauth-redirectreference.grafana='{"kind":"OAuthRedirectReference","apiVersion":"v1","reference":{"kind":"Route","name":"grafana"}}' -n sre-monitoring

#oc annotate service grafana-service service.alpha.openshift.io/serving-cert-secret-name=grafana-tls -n sre-monitoring
```

## Deploy Service Monitoring

```shell
helm template sre-service-monitor --namespace grafana-operator | oc apply -f -
```

## Monitoring the master-api

```shell
helm template sre-service-monitor --namespace openshift-monitoring --values ./master-api-values.yaml | oc apply -f -
```

## Deploy Grafana - connected to platform Prometheus

```shell
export token=$(oc get secret htpasswd -n istio-system -o jsonpath='{.data.rawPassword}' | base64 -d)
helm template grafana-ocp --namespace sre-monitoring --values ./istio-prometheus-values.yaml --set prometheus_datasource.token=$token | oc apply -f -
# fixes for current bugs of the grafana operator
oc annotate serviceaccount grafana-serviceaccount serviceaccounts.openshift.io/oauth-redirectreference.grafana='{"kind":"OAuthRedirectReference","apiVersion":"v1","reference":{"kind":"Route","name":"sre-service-monitoring"}}' -n sre-monitoring
oc annotate service grafana-service service.alpha.openshift.io/serving-cert-secret-name=grafana-tls -n sre-monitoring
```


## Deploy bookinfo and generate load

Follow instructions [here] to deploy OCP Service Mesh and bookinfo, the example app.
Follow the steps below to deploy locust, a load generator

```shell
oc new-project locust
export istio_gateway_url=$(oc get route istio-ingressgateway -n istio-system -o jsonpath='{.spec.host}')
oc create configmap locust-tasks --from-file=tasks.py=./locust/locustfile.py -n locust
export locust_chart_version=$(helm search locust | grep locust | awk '{print $2}')
helm fetch stable/locust --version ${locust_chart_version}
helm template locust-${locust_chart_version}.tgz -n bookinfo-load --namespace locust --set master.config.target-host=http://$istio_gateway_url -f ./locust/values.yaml | oc apply -f -
rm locust-${locust_chart_version}.tgz
oc expose service bookinfo-load-master-svc --port 8089 --name locust -n locust
```
