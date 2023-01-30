

def get_worker_class_from_fullname(fullname):
    parts = fullname.split('@')
    if len(parts) > 1:
        return parts[1]
    else:
        return parts[0]


def get_task_name_from_fullname(fullname):
    parts = fullname.split('.')
    return parts[-1]


def get_task_uuid_from_full_task_id(task_id):
    return task_id.split('.')[0]
