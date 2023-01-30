from collections import namedtuple

ExperienceEntry = namedtuple('ExperienceEntry', 'state action reward next_state')
RemoteExperienceEntry = namedtuple('RemoteExperienceEntry', 'id db_name')
RunCodeTuple = namedtuple('RunCodeTuple', 'run_code db_name')
