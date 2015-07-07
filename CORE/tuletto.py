#!/usr/bin/python2

# imports
import os, signal, sys;
import time;
import subprocess, atexit;

import MySQLdb;
import MySQLdb.cursors;

import urllib2, json;

from pprint import pprint;
from datetime import datetime;

#
# Global variables
#
state = 'start';
activeList = [];
maxConcurrentDownloads = 10;

# MySQL variables
dbConnection = None;
dbName = 'leech';
dbUser = 'root';
dbPassword = 'BP@756cha';

# Aria variables
ariaPort = 'http://127.0.0.1:6800/jsonrpc';
ariaProcess = None;
workingDirectory = '/mnt/hd0';

# Class definitions

# Class "GracefulInterruptHandler" imported from https://gist.github.com/nonZero/2907502
class GracefulInterruptHandler(object):

    def __init__(self, sig=signal.SIGINT):
        self.sig = sig

    def __enter__(self):

        self.interrupted = False
        self.released = False

        self.original_handler = signal.getsignal(self.sig)

        def handler(signum, frame):
            self.release()
            self.interrupted = True

        signal.signal(self.sig, handler)

        return self

    def __exit__(self, type, value, tb):
        self.release()

    def release(self):

        if self.released:
            return False

        signal.signal(self.sig, self.original_handler)

        self.released = True

        return True


# Function definitions
def send2Aria( method, params = [] ):
    jsonreq = json.dumps({
            'jsonrpc':'2.0',
            'id':'backPy',
            'method':method,
            'params':params
        }, encoding='utf8');
    try:
        c = urllib2.urlopen( ariaPort, jsonreq );
        #print "message sent to aria2::" + method;
        return json.loads(c.read());
    except BaseException as e:
        print "Error in send2Aria:: " + method;
        pprint( params );
        print 'Exception error is: %s' % e;
        

def runAria2():
    global ariaProcess;
    FLOG = open('/root/arialog', 'w');
    FERR = open('/root/ariaerr', 'w');
    ariaProcess = subprocess.Popen([
            "aria2c","--enable-rpc", "--dir=" + workingDirectory, "--download-result=full", "--file-allocation=none",
            "--max-connection-per-server=16", "--min-split-size=1M", "--split=16", "--max-overall-download-limit=0",
            "--max-concurrent-downloads=" + str(maxConcurrentDownloads), "--max-resume-failure-tries=5", "--follow-metalink=false"
         ], stdout=FLOG, stderr=FERR);
    i = 0;
    resp = send2Aria( 'aria2.getVersion' , [] );
    while resp is None and i < 10:
        i = i + 1;
        time.sleep(1);
        resp = send2Aria( 'aria2.getVersion' , [] );
    if i == 10:
        print "Could not connect to aria2. exiting..."

def systemDiagnosis():
    global state;
    #
    # Body of systemDiagnosis
    #
    state = 'stable';

def main():
    print "Service started";

    global dbConnection, dbUser, dbPassword, dbName, activeList;

    runAria2();
    systemDiagnosis();

    
    # dbConnection
    dbConnection = MySQLdb.connect( "localhost", dbUser, dbPassword, dbName, cursorclass=MySQLdb.cursors.DictCursor, charset='utf8' );
    dlListFetchCursor = dbConnection.cursor();
    dbConnection.begin();
    
    dlListFetchCursor.execute( """SELECT min(id) as id, user_id, link, file_name, http_user, http_password FROM download_list
                                  WHERE state is null and deleted = 0
                                  GROUP BY user_id
                                  ORDER BY id
                               """ );
    counter = 1;
    with GracefulInterruptHandler(signal.SIGINT) as h1:
        with GracefulInterruptHandler(signal.SIGTERM) as h2:
            while True:
                
                dlListUpdateCursor = dbConnection.cursor();
                dbConnection.begin();
                
                # For each active ID
                for id in activeList:
                    cid = "%016d" % id;
                    res = send2Aria( 'aria2.tellStatus', [ cid, ['gid','status','completedLength','totalLength' , 'errorCode','files']] );
                    if res['result']['status'] == 'paused':
                        # Update UserDB, download_list and activeList
                        try:
                            dlListUpdateCursor.execute( """UPDATE download_list SET state=-2, completed_length=%s
                                                    WHERE id = %s """,
                                                    (res['result']['completedLength'], id,) );
                            dbConnection.commit();
                            activeList.remove(id);
                            send2Aria( 'aria2.remove', [cid] );
                            send2Aria( 'aria2.removeDownloadResult', [cid] );
                            print "Request " + res['result']['gid'] + " paused";
                        except BaseException as e:
                            dbConnection.rollback();
                            print "Exception in pause procedure: %s" % e;
                        
                    elif res['result']['status'] == 'error':
                        # Update UserDB, download_list and activeList
                        try:
                            dlListUpdateCursor.execute( """UPDATE download_list SET state=%s, completed_length=%s
                                                    WHERE id = %s """, ( str(res['result']['errorCode']),
                                                    res['result']['completedLength'], id,) );
                            dbConnection.commit();
                            activeList.remove(id);
                            send2Aria( 'aria2.removeDownloadResult', [cid] );
                            print "Request " + res['result']['gid'] + " got an error with code: " + res['result']['errorCode'];
                        except BaseException as e:
                            dbConnection.rollback();
                            print "Exception in error procedure: %s" % e;
                        
                    elif res['result']['status'] == 'removed':
                        # Update UserDB, download_list and activeList.
                        try:
                            dlListUpdateCursor.execute( """INSERT INTO credit_log ( user_id, credit_change, agent )
                                                           SELECT user_id, %s, user_id FROM download_list WHERE id = %s""",
                                                           ( str( -int (res['result']['completedLength'] ) ), id, ) );
                            dlListUpdateCursor.execute( """UPDATE download_list SET state=-3, completed_length=%s, deleted=1
                                                    WHERE id = %s """, ( res['result']['completedLength'], id,) );
                            dlListUpdateCursor.execute( """UPDATE users SET credit = credit - %s
                                                    WHERE id in ( SELECT user_id FROM download_list WHERE id = %s ) """,
                                                    ( res['result']['completedLength'], id,) );
                            dbConnection.commit();
                            activeList.remove(id);
                            send2Aria( 'aria2.removeDownloadResult', [cid] );
                            print "Request " + res['result']['gid'] + " canceled";
                            # remove file
                            os.remove( res['result']['files'][0]['path'] );
                            os.remove( res['result']['files'][0]['path'] + '.aria2' );
                        except BaseException as e:
                            dbConnection.rollback();
                            print "Exception in remove procedure: %s" % e;
                            
                    elif res['result']['status'] == 'complete':
                        # Update UserDB, download_list and activeList
                        try:
                            dlListUpdateCursor.execute( """INSERT INTO credit_log ( user_id, credit_change, agent )
                                                           SELECT user_id, %s, user_id FROM download_list WHERE id = %s""",
                                                           ( str( -int (res['result']['completedLength'] ) ), id, ) );
                            dlListUpdateCursor.execute( """UPDATE download_list SET state=0, date_completed=%s, completed_length=%s
                                                    WHERE id = %s """, (datetime.now(),
                                                    res['result']['completedLength'], id,) );
                            dlListUpdateCursor.execute( """UPDATE users SET credit = credit - %s
                                                    WHERE id in ( SELECT user_id FROM download_list WHERE id = %s ) """,
                                                    ( res['result']['completedLength'], id,) );
                            dbConnection.commit();
                            activeList.remove(id);
                            send2Aria( 'aria2.removeDownloadResult', [cid] );
                            print "Request " + res['result']['gid'] + " completed";
                        except BaseException as e:
                            dbConnection.rollback();
                            print "Exception in completion procedure: %s" % e;
                # End FOR
                
                # Add a new link if posible
                while int(send2Aria( 'aria2.getGlobalStat' )['result']['numActive']) < maxConcurrentDownloads:
                    # Find next request to be processed
                    row = dlListFetchCursor.fetchone();
                    
                    if row is not None:
                        print "Adding new url: " + row['link'];
                        print "With gid: " + "%016d" % row['id'];
                        # Send request to Aria2
                        send2Aria( 'aria2.addUri', [ [row['link']], {
                                'out':str(row['id']) + "_" + row['file_name'],
                                'gid':"%016d" % row['id'],
                                'http-user':row['http_user'],
                                'http-passwd':row['http_password']
                            } 
                        ] );
                        # Update DataBase
                        activeList.append(row['id']);
                        try:
                            dlListUpdateCursor.execute( """UPDATE download_list SET state=-1, date_started=%s
                                                    WHERE id = %s """, (datetime.now(), row['id'], ) );
                            dbConnection.commit();
                        except:
                            dbConnection.rollback();
                    else:
                        dlListFetchCursor = dbConnection.cursor();
                        dbConnection.begin();
                        dlListFetchCursor.execute( """SELECT min(id) as id, user_id, link, file_name, http_user, http_password FROM download_list
                                                      WHERE state is null and deleted = 0
                                                      GROUP BY user_id
                                                      ORDER BY id
                                                   """ );
                        break;
                # End While
                
                if counter % 150 == 0: # Each 5 mins retry downlaod errors
                    counter = 1;
                    try:
                        dlListUpdateCursor.execute("""UPDATE download_list set state = null WHERE state > 0 and deleted = 0""");
                        dbConnection.commit();
                    except BaseException as e:
                        dbConnection.rollback();
                        print "Exception in retry for error links: %s" % e;
                            
                if h1.interrupted or h2.interrupted:
                    print "Exiting";
                    break;
                
                counter += 1;
                sys.stdout.flush();
                time.sleep(2);
        # End While

@atexit.register
def destruct():
    dlListUpdateCursor = dbConnection.cursor();
    dbConnection.begin();
    for id in activeList:
        cid = "%016d" % id;
        send2Aria('aria2.pauseAll');
        res = send2Aria( 'aria2.tellStatus', [ cid, ['gid','completedLength']] );
        try:
            dlListUpdateCursor.execute( """UPDATE download_list SET state=NULL, completed_length=%s
                                     WHERE id = %s """,
                                     (res['result']['completedLength'], id,) );
            dbConnection.commit();
            print "Request " + cid + " paused";
        except BaseException as e:
            dbConnection.rollback();
            print "Exception in pause downloads on exit: %s" % e;
    
    send2Aria('aria2.shutdown');
    dbConnection.close();







if __name__ == "__main__":
    main();