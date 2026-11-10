// SPDX-License-Identifier: GPL-2.0
/* Correct the tablet port's generated controller address after UART setup. */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <net/bluetooth/bluetooth.h>
#include <net/bluetooth/hci_core.h>

static char *address;
module_param(address, charp, 0400);
MODULE_PARM_DESC(address, "Android public Bluetooth address, XX:XX:XX:XX:XX:XX");
static struct hci_dev *controller;
static int (*original_setup)(struct hci_dev *);
static bdaddr_t identity;

static int find_controller(struct device *dev, void *data)
{
	struct device **found = data;

	if (dev->class && !strcmp(dev->class->name, "bluetooth") &&
	    !strcmp(dev_name(dev), "hci0")) {
		*found = get_device(dev);
		return 1;
	}
	return device_for_each_child(dev, data, find_controller);
}

static int android_setup(struct hci_dev *hdev)
{
	int err = original_setup(hdev);

	if (err)
		return err;
	err = hdev->set_bdaddr(hdev, &identity);
	if (err)
		return err;
	bacpy(&hdev->public_addr, &identity);
	bacpy(&hdev->bdaddr, &identity);
	bt_dev_info(hdev, "Android Bluetooth identity applied: %pMR", &identity);
	return 0;
}

static int __init android_identity_init(void)
{
	unsigned int b[6];
	struct device *uart, *found = NULL;
	int i, err = 0;

	if (!address || strlen(address) != 17 ||
	    sscanf(address, "%2x:%2x:%2x:%2x:%2x:%2x",
		   &b[0], &b[1], &b[2], &b[3], &b[4], &b[5]) != 6)
		return -EINVAL;
	for (i = 0; i < 6; i++)
		identity.b[5-i] = b[i];
	if (!bacmp(&identity, BDADDR_ANY) || (b[0] & 1))
		return -EINVAL;
	uart = bus_find_device_by_name(&platform_bus_type, NULL, "898000.serial");
	if (!uart)
		return -ENODEV;
	device_for_each_child(uart, &found, find_controller);
	put_device(uart);
	if (!found)
		return -ENODEV;
	controller = container_of(found, struct hci_dev, dev);
	mutex_lock(&controller->req_lock);
	hci_dev_lock(controller);
	/* Scope this adapter to the exact Qualcomm tablet UART controller. */
	if (controller->bus != HCI_UART || !controller->setup ||
	    !controller->set_bdaddr || controller->manufacturer != 29)
		err = -ENODEV;
	else if (test_bit(HCI_UP, &controller->flags))
		err = -EBUSY;
	else {
		original_setup = controller->setup;
		controller->setup = android_setup;
	}
	hci_dev_unlock(controller);
	mutex_unlock(&controller->req_lock);
	if (err) {
		hci_dev_put(controller);
		controller = NULL;
	}
	return err;
}

static void __exit android_identity_exit(void)
{
	mutex_lock(&controller->req_lock);
	hci_dev_lock(controller);
	if (controller->setup == android_setup)
		controller->setup = original_setup;
	hci_dev_unlock(controller);
	mutex_unlock(&controller->req_lock);
	hci_dev_put(controller);
}

module_init(android_identity_init);
module_exit(android_identity_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Apply Android Bluetooth identity after TB322FC UART setup");
