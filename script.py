#!/usr/bin/python
import commands
import time
import glob
import re
import os
import ConfigParser
import datetime
import logging

def parse_vms(vm_list):
    '''Take the raw output of get_vms and transform it into a
    list of (uuid, name) tuples for further processing.'''
    result = []

    if vm_list:
        for vm in vm_list.split("\n\n\n"):
            lines = vm.splitlines()
            uuid = lines[0].split(":")[1][1:]
            name = lines[1].split(":")[1][1:]
            result += [(uuid, name)]

    return result


def get_vms(criteria):
    '''Returns a raw string representing the output of Xen's
    tools that list VMs by given criteria.
    :param criteria: str, possible options are:
                    - all - everything
                    - running - only running machines
                    - list - a list of predefined machines'''
    # if criteria == 'all':
    #     result = commands.getoutput('xe vm-list is-control-domain=false'
    #                               ' is-a-snapshot=false')
    # elif criteria == 'running':
    #     result = commands.getoutput('xe vm-list power-state=running'
    #                                   ' is-control-domain=false')
    # elif criteria == 'list':
    #     # get them all, then filter the output by taking only the
    #     # ones you need
    #     result = commands.getoutput('xe vm-list is-control-domain=false'
    #                               ' is-a-snapshot=false')
    result = {
        'all': commands.getoutput('xe vm-list is-control-domain=false'
                                  ' is-a-snapshot=false'),
        'running': commands.getoutput('xe vm-list power-state=running'
                                      ' is-control-domain=false'),
        'list': backup_list,
        'none': None
    }.get(criteria, None)
    logging.info('VMs that will be backed up: %s', result)
    return result


def backup_vm(uuid, filename, timestamp):
    logging.info('Backing up %s to %s', uuid, filename)
    snapshot_uuid = commands.getoutput(
        'xe vm-snapshot uuid=' + uuid + ' new-name-label=' + timestamp)
    commands.getoutput(
        'xe template-param-set is-a-template=false '
        'ha-always-run=false uuid=' + snapshot_uuid)
    commands.getoutput(
        'xe vm-export vm=' + snapshot_uuid + ' filename=' + filename)
    commands.getoutput('xe vm-uninstall uuid=' + snapshot_uuid + ' force=true')


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
    days_old = config.get('Wipe_old_backups', 'days')
    backup_dir = config.get('Backup', 'directory')
    backup_ext = config.get('Backup', 'extension')
    backup_mode = config.get('Backup', 'mode')
    backup_list = config.get('Backup_list', 'backup_list').split(',')

    logging.info('Mounting backup volume')
    commands.getoutput("mount -t " + device + " " + backup_dir)

    wipe_old_backups(int(days_old))



    for (uuid, name) in parse_vms(get_vms(backup_mode)):
         timestamp = time.strftime("%Y%m%d-%H%M", time.gmtime())
         logging.info('Preparing %s %s %s', timestamp, uuid, name)
         filename = "\" " + backup_dir + "/" + timestamp + " " + name + ".xva\""
         backup_vm(uuid, filename, timestamp)

    commands.getoutput("umount -f -l " + backup_dir)