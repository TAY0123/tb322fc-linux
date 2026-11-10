import unittest
from wake_diagnostics import irq_counts, irq_delta, wake_delta


class WakeEvidenceTests(unittest.TestCase):
    def test_sums_per_cpu_interrupt_counts_and_preserves_device_name(self):
        text = '           CPU0 CPU1\n  45: 2 3 GICv3 312 Level qcom_glink\n IPI0: 9 1 Function call\n'
        self.assertEqual(irq_counts(text), {'45': {'count': 5, 'description': 'GICv3 312 Level qcom_glink'}})

    def test_reports_only_increased_known_irq_counts(self):
        first = ' 45: 2 3 GICv3 312 Level qcom_glink\n 99: 7 0 timer\n'
        last = ' 45: 4 4 GICv3 312 Level qcom_glink\n 99: 7 0 timer\n 88: 9 new-device\n'
        self.assertEqual(irq_delta(first, last),
                         [{'irq': 45, 'delta': 3, 'description': 'GICv3 312 Level qcom_glink'}])

    def test_wake_sources_match_by_name_and_distinguish_events_from_wakes(self):
        first = {'wakeup': [{'name': 'usb', 'event_count': '10', 'wakeup_count': '0', 'active_count': '5'}]}
        last = {'wakeup': [{'name': 'usb', 'event_count': '12', 'wakeup_count': '1', 'active_count': '5'}]}
        self.assertEqual(wake_delta(first, last), [{'name': 'usb', 'event_count': 2, 'wakeup_count': 1}])


if __name__ == '__main__':
    unittest.main()
