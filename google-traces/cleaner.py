from argparse import ArgumentParser

from traces import mongo_wrapper
from traces.model.common import clean_duplicates


def get_args():
    parser = ArgumentParser(description='Google Traces Cleaner Arguments')
    parser.add_argument('--db', help='specify the db on which save the results')
    parser.add_argument('-s', '--skip-step', help='comma separated list of steps to skip')
    parser.add_argument('--collection-events', default='collection_events',
                        help='name of the collection for the collection events documents')
    parser.add_argument('--instance-events', default='instance_events',
                        help='name of the collection for the instance events documents')
    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()
    step_to_skip = args.skip_step.split(',') if args.skip_step is not None else []
    if args.db is not None:
        mongo_wrapper.set_db(db_name=args.db)
    if "1" in step_to_skip:
        print('clean collection events skipped')
    else:
        clean_duplicates(args.collection_events)

    if "2" in step_to_skip:
        print('clean instance events skipped')
    else:
        clean_duplicates(args.instance_events)
