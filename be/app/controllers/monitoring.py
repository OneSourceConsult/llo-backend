# import logging
# from prometheus_client import start_http_server, Gauge, Counter

# # --------------------- METRICS DEFINITION ---------------------

# num_clusters = Gauge('clusters_num', 'Number of currently running clusters in all providers')
# num_providers = Gauge('providers_num', 'Number of currently running providers within ClusterAPI')
# num_apps = Gauge('apps_num', 'Number of currently deployed apps via the orchestrator')
# num_components = Gauge('components_num', 'Number of currently deployed components via the orchestrator')

# # logging.info("METRICS INITIALIZED...")


# # --------------------- METRICS DEFINITION ---------------------

# def init_prometheus():
#     # Start up the server to expose the metrics.
#     start_http_server(8000)

#     # logging.info("PROMETHEUS UP AND RUNNING...")

