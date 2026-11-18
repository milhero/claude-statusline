import os
import unittest

from ccsl import rules
from tests.helpers import Sandbox


class TestNormalize(unittest.TestCase):
    def test_windows_paths_get_forward_slashes_and_upper_drive(self):
        self.assertEqual(rules.normalize("c:\\Users\\ana\\proj\\"), "C:/Users/ana/proj")

    def test_trailing_slash_goes_but_root_stays(self):
        self.assertEqual(rules.normalize("/srv/web/"), "/srv/web")
        self.assertEqual(rules.normalize("/"), "/")
        self.assertEqual(rules.normalize("C:/"), "C:/")


class TestClassify(Sandbox):
    def ctx(self, user_rules=None, roots=None):
        return rules.Context(user_rules, roots=roots)

    def test_git_repository_is_the_project(self):
        repo = self.repo("code", "aurora")
        name, rank = self.ctx().classify(repo + "/src/app")
        self.assertEqual((name, rank), ("aurora", "project"))

    def test_deep_layouts_work_without_any_rule(self):
        repo = self.repo("Documents", "GitHub", "org", "aurora")
        self.assertEqual(self.ctx().classify(repo + "/a/b/c")[0], "aurora")

    def test_deleted_subfolder_still_belongs_to_its_repository(self):
        repo = self.repo("code", "aurora")
        self.assertEqual(self.ctx().classify(repo + "/gone/deeper")[0], "aurora")

    def test_worktree_counts_towards_main_repository(self):
        main = self.repo("code", "aurora")
        tree = self.repo("trees", "aurora-fix", worktree_of=main)
        self.assertEqual(self.ctx().classify(tree + "/src")[0], "aurora")

    def test_claude_worktree_inside_repository(self):
        main = self.repo("code", "aurora")
        tree = self.repo("code", "aurora", ".claude", "worktrees", "agent-1", worktree_of=main)
        self.assertEqual(self.ctx().classify(tree)[0], "aurora")

    def test_explicit_rule_beats_git(self):
        repo = self.repo("code", "mono")
        ctx = self.ctx([{"prefix": repo + "/apps/web", "project": "Web", "rank": "project"}])
        self.assertEqual(ctx.classify(repo + "/apps/web/src")[0], "Web")
        self.assertEqual(ctx.classify(repo + "/apps/api")[0], "mono")

    def test_longest_prefix_wins_and_hyphen_prefix_matches_name_start(self):
        ctx = self.ctx([{"prefix": "/srv", "project": "Server", "rank": "project"},
                        {"prefix": "/srv/web/shop-", "project": "Shop", "rank": "project"}])
        self.assertEqual(ctx.classify("/srv/web/shop-v2/x")[0], "Shop")
        self.assertEqual(ctx.classify("/srv/other")[0], "Server")

    def test_rule_prefix_with_tilde(self):
        ctx = self.ctx([{"prefix": "~/notes", "project": "Notes", "rank": "secondary"}])
        self.assertEqual(ctx.classify(str(self.home) + "/notes/a"), ("Notes", "secondary"))

    def test_unknown_rank_assigns_nothing(self):
        ctx = self.ctx([{"prefix": "/x", "project": "X", "rank": "maybe"}])
        self.assertEqual(ctx.classify("/x/y"), (None, "neutral"))

    def test_home_itself_and_temp_are_neutral(self):
        ctx = self.ctx(roots=[str(self.home)])
        self.assertEqual(ctx.classify(str(self.home)), (None, "neutral"))
        self.assertEqual(ctx.classify("/proc/self/x"), (None, "neutral"))
        self.assertEqual(ctx.classify("/private/var/folders/x/y"), (None, "neutral"))

    def test_dotfiles_repository_in_home_does_not_swallow_everything(self):
        (self.home / ".git").mkdir(parents=True)
        self.assertEqual(self.ctx().classify(str(self.home) + "/notes/x"), (None, "neutral"))

    def test_claude_folders_are_neutral_or_secondary(self):
        claude = str(self.claude).replace("\\", "/")
        ctx = self.ctx()
        self.assertEqual(ctx.classify(claude + "/projects/-x/log"), (None, "neutral"))
        self.assertEqual(ctx.classify(claude + "/skills/mine"),
                         (rules.CLAUDE_CONFIG, "secondary"))

    def test_project_roots_for_folders_without_git(self):
        (self.root / "work" / "drafts").mkdir(parents=True)
        root = str(self.root / "work")
        ctx = self.ctx(roots=[root])
        self.assertEqual(ctx.classify(root + "/drafts/a.md")[0], "drafts")
        # A mistyped folder does not become a project of its own.
        self.assertIsNone(ctx.classify(root + "/drafst/a.md")[0])

    def test_a_root_is_never_a_project_itself(self):
        top = self.root / "top"
        (top / "trees").mkdir(parents=True)
        ctx = self.ctx(roots=[str(top), str(top / "trees")])
        self.assertIsNone(ctx.classify(str(top / "trees" / "deleted" / "x"))[0])

    def test_known_roots_outlive_deleted_repositories(self):
        ctx = rules.Context([], known_roots={"/gone/repo/src": "/gone/repo"})
        self.assertEqual(ctx.classify("/gone/repo/src")[0], "repo")

    def test_windows_paths_find_their_repository(self):
        repo = self.repo("code", "aurora")
        windows_style = repo.replace("/", "\\") + "\\src"
        self.assertEqual(self.ctx().classify(windows_style)[0], "aurora")


class TestLoadSave(Sandbox):
    def test_missing_or_broken_file_means_no_rules(self):
        self.assertEqual(rules.load(), [])
        rules.default_path().parent.mkdir(parents=True, exist_ok=True)
        rules.default_path().write_text("{broken", encoding="utf-8")
        self.assertEqual(rules.load(), [])

    def test_round_trip(self):
        rule = {"prefix": "/srv/app", "project": "App", "rank": "project"}
        rules.save([rule])
        self.assertEqual(rules.load(), [rule])

    def test_repos_from_rules_skip_worktrees(self):
        main = self.repo("code", "app")
        tree = self.repo("trees", "app-x", worktree_of=main)
        found = rules.git_repos_from_rules([
            {"prefix": tree, "project": "App", "rank": "project"},
            {"prefix": main, "project": "App2", "rank": "project"}])
        self.assertEqual(found, {"App2": main})


class TestTemp(unittest.TestCase):
    def test_system_temp_dir_is_recognised(self):
        import tempfile
        self.assertTrue(rules.is_temp(os.path.join(tempfile.gettempdir(), "x")))


if __name__ == "__main__":
    unittest.main()
