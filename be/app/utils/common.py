from datetime import datetime
import os
import time
import kubernetes


def timeit(f):
    def timed(*args, **kw):
        ts = time.time()
        result = f(*args, **kw)
        te = time.time()
        print('func:%r args:[%r, %r] took: %.4f sec' %
              (f.__name__, args, kw, te-ts))
        return result
    return timed


def elapsedTime(date):
    start = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    t = int((datetime.now() - start).total_seconds())
    if (t < 60):
        return "%ss" % (t)
    elif (t // 3600 < 24):
        return "%sh" % (t // 3600)
    else:
        days = (t // 3600 // 24)
        return "%sd%sh" % (days, (t - days * 24 * 3600) // 3600)

def get_orchestration_custom_resources():
    # Load Kubernetes configuration from default location
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    # Create Kubernetes API client
    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    api_response = api_instance.list_cluster_custom_object(
        group="charity-project.eu",
        version="v1",
        plural="lowlevelorchestrations"
    )
    
    return api_response

def update_CRD_Status(uid, new_status, type):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    # Create an instance of the Kubernetes API client
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.list_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        
    )
            
    for crd in orchestration_custom_resource["items"]:
        crd_name = crd["metadata"]["name"]
        index = 0
        for component in crd["spec"][type]:
            
            if type == "clusters":
                if (component["name"]) == uid:
                    
                    crd["spec"][type].pop(index)
                    component["status"] = new_status
                    crd["spec"][type].append(component)
                    break
            
            elif type == "apps":
                if component["id"] == uid:
                    
                    crd["spec"][type].pop(index)
                    component["status"] = new_status
                    crd["spec"][type].append(component)
                    break
            
            index += 1
            
    api_instance.patch_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name = crd_name,
            body=crd
        )
    