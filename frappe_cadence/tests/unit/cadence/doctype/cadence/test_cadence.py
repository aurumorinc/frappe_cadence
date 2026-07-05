from frappe.tests import UnitTestCase
from unittest.mock import patch, MagicMock
from frappe_cadence.cadence.doctype.cadence.cadence import determine_sender
import frappe

class TestCadenceSender(UnitTestCase):
    def test_determine_sender_round_robin(self):
        cadence = MagicMock()
        cadence.users = [MagicMock(user="user1"), MagicMock(user="user2"), MagicMock(user="user3")]
        cadence.rule = "Round Robin"
        cadence.last_user = "user1"
        
        # Test basic sequence
        sender = determine_sender(cadence)
        self.assertEqual(sender, "user2")
        cadence.db_set.assert_called_with("last_user", "user2")
        
        # Next
        cadence.last_user = "user2"
        sender = determine_sender(cadence)
        self.assertEqual(sender, "user3")
        
        # Wraparound
        cadence.last_user = "user3"
        sender = determine_sender(cadence)
        self.assertEqual(sender, "user1")
        
    @patch("frappe_cadence.cadence.doctype.cadence.cadence.frappe.get_all")
    def test_determine_sender_load_balancing(self, mock_get_all):
        cadence = MagicMock()
        cadence.users = [MagicMock(user="user1"), MagicMock(user="user2"), MagicMock(user="user3")]
        cadence.rule = "Load Balancing"
        
        # Setup mock db to return counts
        mock_get_all.return_value = [
            MagicMock(sender="user1", cnt=5),
            MagicMock(sender="user2", cnt=2),
            MagicMock(sender="user3", cnt=3)
        ]
        
        sender = determine_sender(cadence)
        self.assertEqual(sender, "user2") # user2 has lowest count
        
    def test_determine_sender_fallback(self):
        cadence = MagicMock()
        cadence.users = []
        cadence.owner = "owner@test.com"
        
        sender = determine_sender(cadence)
        self.assertEqual(sender, "owner@test.com")
