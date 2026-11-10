/*
 * Experimental SM8750 adaptation of the older Qualcomm charger driver's
 * display-blank notification policy. A successful ACK is not proof that the
 * firmware will suppress every notification or that deep suspend is fixed.
 * The caller holds battmgr->lock for every notification-control transaction.
 */
static bool qcom_battmgr_notifications_wanted(struct qcom_battmgr *battmgr)
{
	return !battmgr->panel_following ||
		(battmgr->panel_on && !battmgr->suspend_pending);
}

static int qcom_battmgr_set_notifications(struct qcom_battmgr *battmgr,
					bool enable)
{
	struct qcom_battmgr_enable_request req = {
		.hdr.owner = cpu_to_le32(PMIC_GLINK_OWNER_BATTMGR),
		.hdr.type = cpu_to_le32(PMIC_GLINK_NOTIFY),
		.hdr.opcode = cpu_to_le32(enable ? BATTMGR_REQUEST_NOTIFICATION :
						BATTMGR_DISABLE_NOTIFICATION),
	};
	int ret;

	if (!READ_ONCE(battmgr->service_up))
		return -ENOTCONN;
	if (READ_ONCE(battmgr->notification_state) == enable)
		return 0;

	ret = qcom_battmgr_request(battmgr, &req, sizeof(req));
	if (ret || !READ_ONCE(battmgr->service_up)) {
		WRITE_ONCE(battmgr->notification_state, -1);
		return ret ?: -ENOTCONN;
	}

	WRITE_ONCE(battmgr->notification_state, enable);
	dev_info(battmgr->dev, "firmware notifications %s (panel=%u suspend=%u)\n",
		 enable ? "enabled" : "disabled", battmgr->panel_on,
		 battmgr->suspend_pending);
	return 0;
}

static void qcom_battmgr_refresh_supplies(struct qcom_battmgr *battmgr)
{
	power_supply_changed(battmgr->bat_psy);
	power_supply_changed(battmgr->usb_psy);
}

static int qcom_battmgr_panel_enabled(struct drm_panel_follower *follower)
{
	struct qcom_battmgr *battmgr = container_of(follower, struct qcom_battmgr,
						 panel_follower);
	bool refresh;
	int ret;

	mutex_lock(&battmgr->lock);
	battmgr->panel_on = true;
	refresh = !battmgr->suspend_pending;
	ret = qcom_battmgr_set_notifications(battmgr,
				qcom_battmgr_notifications_wanted(battmgr));
	mutex_unlock(&battmgr->lock);
	if (ret) {
		dev_warn(battmgr->dev, "panel notification restore failed: %d\n", ret);
		schedule_work(&battmgr->enable_work);
	}
	if (refresh)
		qcom_battmgr_refresh_supplies(battmgr);
	return 0;
}

static int qcom_battmgr_panel_disabling(struct drm_panel_follower *follower)
{
	struct qcom_battmgr *battmgr = container_of(follower, struct qcom_battmgr,
						 panel_follower);
	int ret;

	mutex_lock(&battmgr->lock);
	battmgr->panel_on = false;
	ret = qcom_battmgr_set_notifications(battmgr, false);
	mutex_unlock(&battmgr->lock);
	if (ret)
		dev_warn(battmgr->dev, "panel notification pause failed: %d\n", ret);
	/* Display blanking still works; suspend preparation retries the command. */
	return 0;
}

static const struct drm_panel_follower_funcs qcom_battmgr_panel_funcs = {
	.panel_enabled = qcom_battmgr_panel_enabled,
	.panel_disabling = qcom_battmgr_panel_disabling,
};

static int qcom_battmgr_pm_notify(struct notifier_block *nb,
				unsigned long action, void *unused)
{
	struct qcom_battmgr *battmgr = container_of(nb, struct qcom_battmgr,
						 pm_notifier);
	int restore_ret;
	int ret;

	if (action != PM_SUSPEND_PREPARE && action != PM_POST_SUSPEND)
		return NOTIFY_DONE;

	if (action == PM_SUSPEND_PREPARE) {
		/* Block a service-restart worker before draining existing work. */
		mutex_lock(&battmgr->lock);
		battmgr->suspend_pending = true;
		mutex_unlock(&battmgr->lock);
		cancel_work_sync(&battmgr->enable_work);
	}

	mutex_lock(&battmgr->lock);
	if (action == PM_POST_SUSPEND)
		battmgr->suspend_pending = false;
	ret = qcom_battmgr_set_notifications(battmgr,
				qcom_battmgr_notifications_wanted(battmgr));
	if (ret && action == PM_SUSPEND_PREPARE) {
		/* A failing notifier must undo its own preparation on an abort. */
		battmgr->suspend_pending = false;
		WRITE_ONCE(battmgr->notification_state, -1);
		restore_ret = qcom_battmgr_set_notifications(battmgr,
				qcom_battmgr_notifications_wanted(battmgr));
		if (restore_ret)
			dev_warn(battmgr->dev, "notification rollback failed: %d\n",
				 restore_ret);
	}
	mutex_unlock(&battmgr->lock);
	if (ret) {
		dev_warn(battmgr->dev, "sleep notification control failed: %d\n", ret);
		schedule_work(&battmgr->enable_work);
	}
	if (action == PM_POST_SUSPEND)
		qcom_battmgr_refresh_supplies(battmgr);
	return action == PM_SUSPEND_PREPARE ? notifier_from_errno(ret) : NOTIFY_OK;
}

static void qcom_battmgr_unregister_pm(void *data)
{
	unregister_pm_notifier(data);
}
