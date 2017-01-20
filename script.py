#!/usr/bin/python
import commands
import time
import glob
import re
import os
import ConfigParser
import datetime
import logging
import subprocess

def parse_vms(raw_output, uuid_filter=None):
    '''Take the raw output of get_vms and transform it into a
    list of (uuid, name) tuples for further processing.
    :param uuid_filter: list of strings, which represents UUIDs
                        that must be included in the result,
                        omitting everything else'''
    machines = {}

    if raw_output:
        for vm in raw_output.split("\n\n\n"):
            lines = vm.splitlines()
            uuid = lines[0].split(":")[1][1:]
            name = lines[1].split(":")[1][1:]
            machines[uuid] = name

    if uuid_filter:
        # if a filter was given, delete all the VMs that are not
        # explicitly mentioned in the filter list 
        for uuid in machines.keys():
            if uuid not in uuid_filter:
                del machines[uuid]

    # transform it into a list of tuples, as the rest of the
    # program expects
    result = [(uuid, name) for uuid, name in machines.iteritems()]
    return result


def get_vms(criteria):
    '''Returns a raw string representing the output of Xen's
    tools that list VMs by given criteria.
    :param criteria: str, possible options are:
                    - all - everything
                    - running - only running machines'''
    result = {
        'all': commands.getoutput('xe vm-list is-control-domain=false'
                                  ' is-a-snapshot=false'),
        'running': commands.getoutput('xe vm-list power-state=running'
                                      ' is-control-domain=false'),
    }.get(criteria, None)
    return result


def backup_vm(uuid, filename, timestamp):
    '''Backup VM to a file
    :param uuid:    str, identifier of the machine
    :param filename:    str, full path to file where to back up
    :param timestamp:   str, TODO get rid of this one, timestamp
                        to be used as a part of the label of the
                        backup machine'''
    logging.info('Backing up %s to %s', uuid, filename)
    snapshot_uuid = commands.getoutput(
        'xe vm-snapshot uuid=' + uuid + ' new-name-label=' + timestamp)
    logging.debug('Produced snapshot %s', snapshot_uuid)

    cmd = 'xe template-param-set is-a-template=false ha-always-run=false uuid=' + snapshot_uuid
    status = subprocess.call(cmd.split())
    logging.debug('Setting template-param to False, status: %s', status)

    cmd = 'xe vm-export vm=%s filename=%s)' % (snapshot_uuid, filename)
    status = subprocess.call(cmd.split())
    logging.debug('Exorting VM status: %s', status)

    cmd = 'xe vm-uninstall uuid=%s force=true' % (snapshot_uuid)
    status = subprocess.call(cmd.split())
    logging.debug('Export complete, status: %s', status)


def wipe_old_backups(days_old):
    logging.info('Wiping backups older than %i days', days_old)
    os.chdir(backup_dir)
    backup_all = glob.glob('*.xva')

    date_pattern = re.compile('(\d*-\d*).*')
    for backup_name in backup_all:
        backup_date = date_pattern.match(backup_name)
        time_obj = datetime.datetime(*(time.strptime(backup_date.group(1), "%Y%m%d-%H%M")[0:5]))

        if abs((datetime.datetime.now() - time_obj).days) > days_old:
            try:
                os.remove(backup_name)
                logging.info('Removed `%s`', backup_name)
            except OSError, err:
                logging.exception('Could not remove `%s`', backup_name)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)-15s %(levelname)5s - %(message)s')

    config = ConfigParser.RawConfigParser()
    config.read(r'vm_backup.cfg')

    device = config.get('Backup', 'device')
    days_old = config.get('Backup', 'wipe_days')
    backup_dir = config.get('Backup', 'directory')
    backup_ext = config.get('Backup', 'extension')
    backup_mode = config.get('Backup', 'mode')
    backup_fs = config.get('Backup', 'filesys')
    backup_list = config.get('Backup_list', 'backup_list').split(',')

    mount_cmd = "mount -t %s %s %s" % (backup_fs, device, backup_dir)
    logging.info('Mounting backup volume with `%s`', mount_cmd)
    status = subprocess.call(mount_cmd.split())
    logging.info('Result: %s', status)

    # wipe old backups
    wipe_old_backups(int(days_old))


    if backup_mode == 'list':
        logging.info('Backup predefined list of VMs')
        for (uuid, name) in parse_vms(get_vms('all'), backup_list):
            timestamp = time.strftime("%Y%m%d-%H%M", time.gmtime())
            logging.info('Preparing %s %s %s', timestamp, uuid, name)
            filename = "\" " + backup_dir + "/" + timestamp + " " + name + ".xva\""
            backup_vm(uuid, filename, timestamp)
    else:
        # operate as usual
        for (uuid, name) in parse_vms(get_vms(backup_mode)):
             timestamp = time.strftime("%Y%m%d-%H%M", time.gmtime())
             logging.info('Preparing %s %s %s', timestamp, uuid, name)
             filename = "\" " + backup_dir + "/" + timestamp + " " + name + ".xva\""
             backup_vm(uuid, filename, timestamp)

    logging.info('Unmounting `%s`', backup_dir)
    commands.getoutput("umount -f -l " + backup_dir)
    logging.info('Finish')