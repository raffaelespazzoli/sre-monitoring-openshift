# SRE Monitoring for OCP

## Prometheus and Grafana deployment

The following are the steps to deploy a parallel grafana/prometheus/alert-manager stack to what comes up with ServiceMesh

### Preparation

```shell
export istio_cp_namespace=istio-system
export deploy_namespace=sre-monitoring
export istio_cp_name=basic-install

oc new-project ${deploy_namespace}
```

### cluster-admin-tasks

These must be run by a cluster admin.

```shell
#Get a list of members to add a rolebinding using grafanadatasource-prometheus-istio-system.yaml in each control plane member namespace
echo "members: $(oc get ServiceMeshMemberRoll/default -n ${istio_cp_namespace} -o jsonpath="{.spec.members}" | sed s'/ /, /g')" > /tmp/members.yaml

export basicAuthPassword=$(oc extract secret/grafana-datasources -n openshift-monitoring --keys=prometheus.yaml --to=- | grep -zoP '"basicAuthPassword":\s*"\K[^\s,]*(?=\s*",)')

oc adm policy add-cluster-role-to-group system:auth-delegator system:serviceaccounts:${deploy_namespace} --rolebinding-name=oauth-proxy-serviceaccounts

helm template cluster-admin-tasks --namespace ${deploy_namespace} --set secrets.basicAuthPassword=${basicAuthPassword} --set istio_control_plane.namespace=${istio_cp_namespace} -f /tmp/members.yaml | oc apply -f -
```

### sre-admin-operators

These tasks must be run by an admin on the ${deploy_namespace} project.

```shell
helm template sre-admin-operators --namespace ${deploy_namespace} | oc apply -f -

#Wait about 5 minutes for the prometheus operator to install
```

### sre-admin-tasks

These tasks must be run by an admin on both ${deploy_namespace} and ${istio_cp_namespace} projects.

```shell

export cert_chain_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['cert-chain\.pem']}")
export key_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['key\.pem']}")
export root_cert_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['root-cert\.pem']}")

helm template sre-admin-tasks --namespace ${deploy_namespace} --set istio_control_plane.name=${istio_cp_name} --set istio_control_plane.namespace=${istio_cp_namespace} --set istio_cert.cert_chain=${cert_chain_pem} --set istio_cert.key=${key_pem} --set istio_cert.root_cert=${root_cert_pem} --set prometheus_datasource.openshift_monitoring.password=$(oc extract secret/openshift-monitoring-prometheus -n ${deploy_namespace} --keys=basicAuthPassword --to=-) | oc apply -f -

#wait a few minutes for the prometheus operator to install the statefulset
oc patch statefulset/prometheus-sre-prometheus --type='json' -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-name=default" }, {"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--discovery.member-roll-namespace='${istio_cp_namespace}'" }]' -n ${deploy_namespace}

```
