#!/usr/bin/env python3
"""Compile and exercise the actual candidate C state/response handlers on host."""
from pathlib import Path
import subprocess
import tempfile
import sys

base = Path(__file__).resolve().parent
source = Path(sys.argv[1]).read_text() if len(sys.argv) == 2 else (base / 'qcom_battmgr.c').read_text()

def function(name):
    start = source.index('static ', source.index(name) - 100)
    # Find the declaration directly preceding the requested function name.
    start = source.rfind('\nstatic ', 0, source.index(name)) + 1
    end = source.index('\n}', source.index(name)) + 2
    return source[start:end]

prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
typedef uint32_t __le32;
#define cpu_to_le32(x) (x)
#define le32_to_cpu(x) (x)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,y) ((x)=(y))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define PMIC_GLINK_OWNER_BATTMGR 32778
#define PMIC_GLINK_NOTIFY 2
#define BATTMGR_REQUEST_NOTIFICATION 4
#define BATTMGR_DISABLE_NOTIFICATION 5
#define BATTMGR_NOTIFICATION 7
#define QCOM_BATTMGR_SC8280XP 1
#define QCOM_BATTMGR_X1E80100 2
#define PM_SUSPEND_PREPARE 1
#define PM_POST_SUSPEND 2
#define NOTIFY_DONE 0
#define NOTIFY_OK 1
#define SERVREG_SERVICE_STATE_UP 1
#define dev_info(...) ((void)0)
#define dev_warn(...) ((void)0)
#define dev_err(...) ((void)0)
struct pmic_glink_hdr { __le32 owner, type, opcode; };
struct qcom_battmgr_enable_request {
 struct pmic_glink_hdr hdr;
 __le32 battery_id, power_state, low_capacity, high_capacity;
};
struct drm_panel_follower { int unused; };
struct drm_panel_follower_funcs {
 int (*panel_enabled)(struct drm_panel_follower *);
 int (*panel_disabling)(struct drm_panel_follower *);
};
struct notifier_block { int unused; };
struct work_struct { int scheduled, cancelled; };
struct qcom_battmgr {
 bool service_up, panel_following, panel_on, suspend_pending;
 int notification_state, lock, error, ack, variant;
 u32 pending_opcode;
 struct drm_panel_follower panel_follower;
 struct notifier_block pm_notifier;
 struct work_struct enable_work;
 struct { bool current_limit_set; u32 requested_current_limit; } usb;
 void *dev, *bat_psy, *usb_psy;
};
static int count, sent[32], plan[32], plans, refreshes, notifications, responses;
static int notifier_from_errno(int error) { return error ? -1 : NOTIFY_OK; }
static void mutex_lock(int *lock) { assert(!*lock); *lock=1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock=0; }
static void schedule_work(struct work_struct *work) { work->scheduled++; }
static void cancel_work_sync(struct work_struct *work) { work->cancelled++; }
static void unregister_pm_notifier(void *data) { (void)data; }
static void power_supply_changed(void *psy) { (void)psy; refreshes++; }
static void complete(int *ack) { (*ack)++; }
static int qcom_battmgr_set_usb_current_limit(struct qcom_battmgr *b, u32 limit)
{ (void)b; (void)limit; return 0; }
static void qcom_battmgr_notification(struct qcom_battmgr *b, const void *data, size_t len)
{ (void)b; (void)data; (void)len; notifications++; }
static void qcom_battmgr_sc8280xp_callback(struct qcom_battmgr *b, const void *data, size_t len)
{ (void)b; (void)data; (void)len; responses++; }
static void qcom_battmgr_sm8350_callback(struct qcom_battmgr *b, const void *data, size_t len)
{ (void)b; (void)data; (void)len; responses++; }
static int qcom_battmgr_request(struct qcom_battmgr *b, void *data, size_t len)
{
 struct qcom_battmgr_enable_request *req=data;
 assert(b->lock && len==28 && req->hdr.owner==32778 && req->hdr.type==2);
 assert(!req->battery_id && !req->power_state && !req->low_capacity && !req->high_capacity);
 assert(req->hdr.opcode==4 || req->hdr.opcode==5);
 assert(count < 32);
 sent[count]=req->hdr.opcode;
 return count < plans ? plan[count++] : (count++, 0);
}
static struct qcom_battmgr fresh(bool following)
{
 count=plans=refreshes=notifications=responses=0;
 memset(sent,0,sizeof(sent)); memset(plan,0,sizeof(plan));
 return (struct qcom_battmgr){ .service_up=true, .panel_following=following,
                              .notification_state=-1 };
}
'''
tests = r'''
int main(void)
{
 struct qcom_battmgr b=fresh(true);
 struct pmic_glink_hdr hdr={.owner=32778,.type=2,.opcode=5};
 int passed=0;
 /* Blank display from unknown state sends the exact vendor request. */
 qcom_battmgr_panel_disabling(&b.panel_follower);
 assert(count==1 && sent[0]==5 && b.notification_state==0); passed++;
 /* Repeated display blank is idempotent. */
 qcom_battmgr_panel_disabling(&b.panel_follower);
 assert(count==1); passed++;
 /* Display unblank restores notifications and refreshes battery/USB. */
 qcom_battmgr_panel_enabled(&b.panel_follower);
 assert(count==2 && sent[1]==4 && b.notification_state==1 && refreshes==2); passed++;
 /* Sleep while screen is on suppresses notifications. */
 assert(qcom_battmgr_pm_notify(&b.pm_notifier,PM_SUSPEND_PREPARE,NULL)==NOTIFY_OK);
 assert(count==3 && sent[2]==5 && b.suspend_pending && b.enable_work.cancelled==1); passed++;
 /* Firmware restart worker cannot re-enable during sleep preparation. */
 qcom_battmgr_pdr_notify(&b,SERVREG_SERVICE_STATE_UP);
 assert(b.notification_state==-1 && b.enable_work.scheduled==1);
 qcom_battmgr_enable_worker(&b.enable_work);
 assert(count==4 && sent[3]==5 && b.notification_state==0); passed++;
 /* A panel enable during suspend must also keep the subscription disabled. */
 qcom_battmgr_panel_enabled(&b.panel_follower);
 assert(count==4 && refreshes==2); passed++;
 /* Resume, including another driver's aborted sleep, restores screen-on state. */
 qcom_battmgr_pm_notify(&b.pm_notifier,PM_POST_SUSPEND,NULL);
 assert(count==5 && sent[4]==4 && !b.suspend_pending && refreshes==4); passed++;
 /* Screen-off resume follows vendor policy until unblank. */
 qcom_battmgr_panel_disabling(&b.panel_follower);
 qcom_battmgr_pm_notify(&b.pm_notifier,PM_SUSPEND_PREPARE,NULL);
 qcom_battmgr_pm_notify(&b.pm_notifier,PM_POST_SUSPEND,NULL);
 assert(count==6 && b.notification_state==0 && !b.suspend_pending); passed++;
 /* Disable timeout aborts suspend and actively restores the awake state. */
 b=fresh(true); b.panel_on=true; b.notification_state=1;
 plan[0]=-ETIMEDOUT; plans=1;
 assert(qcom_battmgr_pm_notify(&b.pm_notifier,PM_SUSPEND_PREPARE,NULL)==-1);
 assert(count==2 && sent[0]==5 && sent[1]==4 && !b.suspend_pending);
 assert(b.notification_state==1 && b.enable_work.scheduled==1); passed++;
 /* Failed rollback retains unknown state, clears suspend guard, queues retry. */
 b=fresh(true); b.panel_on=true; plan[0]=plan[1]=-ETIMEDOUT; plans=2;
 qcom_battmgr_pm_notify(&b.pm_notifier,PM_SUSPEND_PREPARE,NULL);
 assert(b.notification_state==-1 && !b.suspend_pending && b.enable_work.scheduled); passed++;
 /* A screen blank failure is retried at suspend, without blocking the display. */
 b=fresh(true); b.panel_on=true; plan[0]=-ETIMEDOUT; plans=1;
 assert(qcom_battmgr_panel_disabling(&b.panel_follower)==0);
 assert(b.notification_state==-1);
 assert(qcom_battmgr_pm_notify(&b.pm_notifier,PM_SUSPEND_PREPARE,NULL)==NOTIFY_OK);
 assert(count==2 && sent[0]==5 && sent[1]==5 && b.notification_state==0); passed++;
 /* A disconnected remote is never recorded as having accepted a command. */
 b=fresh(true); b.service_up=false;
 qcom_battmgr_panel_enabled(&b.panel_follower);
 assert(!count && b.notification_state==-1 && b.enable_work.scheduled==1); passed++;
 /* Remote up after a restart restores the current display policy. */
 qcom_battmgr_pdr_notify(&b,SERVREG_SERVICE_STATE_UP);
 qcom_battmgr_enable_worker(&b.enable_work);
 assert(count==1 && sent[0]==4); passed++;
 /* Boards without the opt-in panel retain normal notification enable behavior. */
 b=fresh(false); qcom_battmgr_enable_worker(&b.enable_work);
 assert(count==1 && sent[0]==4 && b.notification_state==1); passed++;
 /* Truncated control packets cannot access a header or complete the request. */
 b=fresh(true); b.pending_opcode=5; b.error=-1;
 qcom_battmgr_callback(&hdr,0,&b);
 assert(!b.ack && b.error==-1); passed++;
 /* A late enable ACK cannot satisfy the disable transaction. */
 hdr.opcode=4; qcom_battmgr_callback(&hdr,sizeof(hdr),&b);
 assert(!b.ack && b.error==-1); passed++;
 /* Header-only matching replies are accepted, as in the vendor driver. */
 hdr.opcode=5; qcom_battmgr_callback(&hdr,sizeof(hdr),&b);
 assert(b.ack==1 && b.error==0); passed++;
 /* Unsolicited control ACKs have no pending transaction to complete. */
 b.pending_opcode=0; qcom_battmgr_callback(&hdr,sizeof(hdr),&b);
 assert(b.ack==1); passed++;
 /* Incoming notifications remain delivered, even while suppression is requested. */
 hdr.opcode=7; b.notification_state=0;
 qcom_battmgr_callback(&hdr,sizeof(hdr),&b);
 assert(notifications==1 && b.ack==1); passed++;
 /* A late property reply also cannot satisfy a disable transaction. */
 hdr.opcode=0x30; b.pending_opcode=5;
 qcom_battmgr_callback(&hdr,sizeof(hdr),&b);
 assert(!responses && b.ack==1); passed++;
 /* Matching ordinary property-response dispatch is retained. */
 b.pending_opcode=0x30; qcom_battmgr_callback(&hdr,sizeof(hdr),&b);
 assert(responses==1); passed++;
 printf("%d actual-C notification lifecycle/ACK checks passed\n",passed);
}
'''
code = prefix + (base / 'notification-control.c').read_text() + '\n'
for name in ['qcom_battmgr_enable_worker(', 'qcom_battmgr_pdr_notify(', 'qcom_battmgr_callback(']:
    code += function(name) + '\n'
code += tests
with tempfile.TemporaryDirectory() as directory:
    cpath = Path(directory) / 'notification_control.c'
    cpath.write_text(code)
    binary = Path(directory) / 'test'
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                    '-Wno-unused-parameter', '-Wno-unused-const-variable', '-fsanitize=address,undefined',
                    '-g', str(cpath), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
