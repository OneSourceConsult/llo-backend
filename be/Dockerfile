FROM python:3.9-slim-buster

WORKDIR /

#install deps: curl kubectl #iptables wireguard-tools  && \ 
RUN apt-get update \
&& apt-get install -y python3-pip git curl wget file && \
    # clean-up
    rm -rf /root/.cache && mkdir -p /root/.cache && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

ENV CAPI_LATEST_VERSION="v1.3.1"
RUN curl -sLo /usr/local/bin/clusterctl https://github.com/kubernetes-sigs/cluster-api/releases/download/${CAPI_LATEST_VERSION}/clusterctl-linux-amd64 \
&& chmod +x /usr/local/bin/clusterctl

ENV KUBE_LATEST_VERSION="v1.25.0"
RUN curl -sLo /usr/local/bin/kubectl https://dl.k8s.io/release/${KUBE_LATEST_VERSION}/bin/linux/amd64/kubectl \
&& chmod +x /usr/local/bin/kubectl

ENV LIQO_CLI_LATEST_VERSION="v0.7.2"
RUN curl --fail -LS https://github.com/liqotech/liqo/releases/download/${LIQO_CLI_LATEST_VERSION}/liqoctl-linux-amd64.tar.gz | tar -xz \
&& install -o root -g root -m 0755 liqoctl /usr/local/bin/liqoctl

ENV YQ_LATEST_VERSION="v4.30.6"
RUN curl -sLo /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/${YQ_LATEST_VERSION}/yq_linux_amd64 \
&& chmod +x /usr/local/bin/yq

RUN curl -sL https://get.helm.sh/helm-v3.12.0-linux-amd64.tar.gz | tar -zxv \
&& mv linux-amd64/helm /usr/local/bin/helm && chmod +x /usr/local/bin/helm

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

#clusterapi configs & provider settings
COPY app /app/
COPY .config/ /app/.config

EXPOSE 5000
CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=5000"]