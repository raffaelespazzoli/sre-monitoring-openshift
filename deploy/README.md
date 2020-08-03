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

export cluster_admin_tasks_release_name=cluster-admin-tasks

helm upgrade -i ${cluster_admin_tasks_release_name} -n ${deploy_namespace} --set secrets.basicAuthPassword=${basicAuthPassword} --set istio_control_plane.namespace=${istio_cp_namespace} -f /tmp/members.yaml cluster-admin-tasks
```

### sre-admin-operators

These tasks must be run by an admin on the ${deploy_namespace} project.

```shell
export sre_admin_operators_release_name=sre-admin-operators

helm upgrade -i ${sre_admin_operators_release_name} -n ${deploy_namespace} sre-admin-operators

#Wait about 5 minutes for the prometheus operator to install
```

Optional: make future prometheus operator upgrades require Manual Approval

```sh
oc patch subscription prometheus-operator --type='json' -p='[{"op": "replace", "path": "/spec/installPlanApproval", "value":"Manual"}]' -n ${deploy_namespace}
```

### sre-admin-tasks

These tasks must be run by an admin on both ${deploy_namespace} and ${istio_cp_namespace} projects.

```shell
export cert_chain_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['cert-chain\.pem']}")
export key_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['key\.pem']}")
export root_cert_pem=$(oc get secret -n ${istio_cp_namespace} istio.default -o jsonpath="{.data['root-cert\.pem']}")

export sre_admin_tasks_release_name=sre-admin-tasks

helm upgrade -i ${sre_admin_tasks_release_name} -n ${deploy_namespace} --set istio_control_plane.name=${istio_cp_name} --set istio_control_plane.namespace=${istio_cp_namespace} --set istio_cert.cert_chain=${cert_chain_pem} --set istio_cert.key=${key_pem} --set istio_cert.root_cert=${root_cert_pem} --set prometheus_datasource.openshift_monitoring.password=$(oc extract secret/openshift-monitoring-prometheus -n ${deploy_namespace} --keys=basicAuthPassword --to=-) sre-admin-tasks
```

### cleanup

```sh
helm delete ${sre_admin_tasks_release_name} -n ${deploy_namespace}
helm delete ${sre_admin_operators_release_name} -n ${deploy_namespace}
helm delete ${cluster_admin_tasks_release_name} -n ${deploy_namespace}
```
