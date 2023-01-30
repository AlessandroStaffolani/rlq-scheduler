from argparse import ArgumentParser

from traces import mongo_wrapper
from traces.model.common import export_dataset


def get_args():
    parser = ArgumentParser(description='Google Traces Export Arguments')
    parser.add_argument('dataset',
                        help='name of the collection storing the dataset')
    parser.add_argument('output', help='saving path, must be a json file')
    parser.add_argument('--scaling', default=1000000*60*60*24,
                        help=f'scaling factor applied to times, original times are in microseconds.'
                             f' Default {1000000*60*60*24}')
    parser.add_argument('--db', help='specify the db on which save the results')
    parser.add_argument('--indent', type=int, help='indent parameter for json dump')
    return parser.parse_args()


if __name__ == "__main__":
    args = get_args()
    if args.db is not None:
        mongo_wrapper.set_db(db_name=args.db)
    assert args.output.endswith('.json'), 'output must be a json file'
    export_dataset(args.dataset, args.scaling, args.output, args.indent)
    print(f'dataset from {args.dataset} exported in {args.output} with success')
