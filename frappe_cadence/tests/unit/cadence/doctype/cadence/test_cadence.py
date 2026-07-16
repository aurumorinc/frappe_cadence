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
        
    @patch("frappe_cadence.cadence.doctype.cadence.cadence.frappe.db.sql")
    def test_determine_sender_load_balancing(self, mock_sql):
        cadence = MagicMock()
        cadence.users = [MagicMock(user="user1"), MagicMock(user="user2"), MagicMock(user="user3")]
        cadence.rule = "Load Balancing"
        
        # Setup mock db to return counts
        mock_sql.return_value = [
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

class TestCadenceAstToFilters(UnitTestCase):
    def test_ast_to_filters(self):
        from frappe_cadence.cadence.doctype.cadence.cadence import Cadence
        import ast

        cadence = Cadence({"doctype": "Cadence"})
        
        # Is / Is Not
        tree = ast.parse('doc.email is "set"', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["email", "is", "set"]])
        
        tree = ast.parse('doc.email is "not set"', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["email", "is", "not set"]])
        
        # Eq / NotEq
        tree = ast.parse('doc.status == "New"', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["status", "=", "New"]])
        
        tree = ast.parse('doc.status != "Lost"', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["status", "!=", "Lost"]])
        
        # Gt / Lt / GtE / LtE
        tree = ast.parse('doc.age > 18', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["age", ">", 18]])
        
        tree = ast.parse('doc.age < 65', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["age", "<", 65]])
        
        tree = ast.parse('doc.age >= 18', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["age", ">=", 18]])
        
        tree = ast.parse('doc.age <= 65', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["age", "<=", 65]])
        
        # In / NotIn
        tree = ast.parse('doc.status in ["New", "Open"]', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["status", "in", ["New", "Open"]]])
        
        tree = ast.parse('doc.status not in ["Lost"]', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["status", "not in", ["Lost"]]])
        
        # Like / Not Like
        tree = ast.parse('doc.email == ["like", "%@example.com"]', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["email", "like", "%@example.com"]])

        tree = ast.parse('doc.email == ["not like", "%@spam.com"]', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["email", "not like", "%@spam.com"]])
        
        # Compound (And)
        tree = ast.parse('doc.status == "New" and doc.email is "set"', mode='eval')
        self.assertEqual(cadence._ast_to_filters(tree.body), [["status", "=", "New"], ["email", "is", "set"]])
