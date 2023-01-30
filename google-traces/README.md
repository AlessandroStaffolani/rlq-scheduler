# google-traces-utils

Set of scripts for downloading and processing the google cluster traces data. Reference [here](https://drive.google.com/file/d/10r6cnJ5cJ89fPWCgj7j4LtLBqYN9RiI9/view)

## Install

1. clone the repo
2. install python requirements `pip install -r requirements.txt`
3. (optional) the scripts require a writing connection to a mongo db instance. If it is not available start the provided docker compose `docker compose up -d`
4. install `gsutil`. Instructions [here](https://cloud.google.com/storage/docs/gsutil_install)
5. create the `.env` file with the information needed for connecting to your mongo db instance (if not available see step 3). A sample of env file is provided in `.env.sample`

## start

```shell
python traces.py gs://clusterdata_2019_a/
```

see the full list of parameters using ``python traces.py -h``

## Export

Once the pipeline has finished, it is possible to export the dataset files to use in the RLQ for the experiments. To export run the following command:

```shell
python export_dataset.py tasks_dataset dataset.json
```

see the full list of parameters using ``python traces.py -h``