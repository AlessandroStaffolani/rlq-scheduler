from argparse import ArgumentParser

from traces import logger, mongo_wrapper
from traces.downloader import list_bucket_files, TableNames
from traces.pipeline import collection_events_pipeline, instance_events_pipeline, task_classes_and_dataset_pipeline, \
    extract_dataset_pipeline, count_jobs_types


def get_args():
    parser = ArgumentParser(description='Google Traces Pipeline Arguments')
    parser.add_argument('bucket', help='name of the bucket on GCS')
    parser.add_argument('classes', type=int, help='number of task classes to extract from the dataset')
    parser.add_argument('-n', '--n-per-table', default=-1, type=int,
                        help='specify how many files for table do you want to download')
    parser.add_argument('-p', '--parallel', type=int, default=2,
                        help='specify the number of parallel threads to use for downloading the traces')
    parser.add_argument('-o', '--output', default='data', help='specify the folder where the traces are downloaded')
    parser.add_argument('-s', '--skip-step', help='comma separated list of steps to skip')
    parser.add_argument('--max-per-machine', default='1', help='filter the collection with max-per-machine')
    parser.add_argument('--event-type', help='filter only instances with event-type')
    parser.add_argument('--db', help='specify the db on which save the results')
    parser.add_argument('--dataset-collection', default='tasks_dataset',
                        help='specify the name of collection in which the dataset will be saved. '
                             'Default: "tasks_dataset"')
    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()
    step_to_skip = args.skip_step.split(',') if args.skip_step is not None else []
    logger.info('Google Traces Pipeline Welcome')
    if args.db is not None:
        mongo_wrapper.set_db(db_name=args.db)
    logger.info('Step 1 | Gathering files info')
    bucket_info = list_bucket_files(args.bucket, step=1)
    logger.info('Step 2 | Starting collection events pipeline')
    if '2' in step_to_skip:
        logger.info('Step 2 | Skipped')
    else:
        collection_events_pipeline(
            args.output,
            bucket_info[TableNames.CollectionEvent],
            args.parallel,
            args.max_per_machine,
            step=2)
    logger.info('Step 3 | Starting instance events pipeline')
    if '3' in step_to_skip:
        logger.info('Step 3 | Skipped')
    else:
        instance_events_pipeline(args.output, bucket_info[TableNames.InstanceEvent], args.parallel, step=3)
    logger.info('Step 4 | Starting generation of task and worker classes')
    if '4' in step_to_skip:
        logger.info('Step 4 | Skipped')
    else:
        task_classes_and_dataset_pipeline(args.parallel, step=4)
    if '5' in step_to_skip:
        logger.info('Step 5 | Skipped')
    else:
        extract_dataset_pipeline(args.classes, args.dataset_collection, step=5)
    if '6' in step_to_skip:
        logger.info('Step 6 | Skipped')
    else:
        count_jobs_types(args.output, bucket_info[TableNames.CollectionEvent], args.parallel, step=6)
    logger.info('Completed with success')

