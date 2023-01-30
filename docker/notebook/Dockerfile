FROM cloud.canister.io:5000/ale8193/base

WORKDIR /usr/src/jupyter

COPY requirements/notebook.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY docker/notebook/run.sh ./
RUN chmod +x /usr/src/jupyter/run.sh

CMD ["/bin/bash", "run.sh"]