"""Cross-source duplicate fixtures that differ only in club-name form must merge; look-alikes must not.

Positive pairs are real cross-source duplicates seen in the live feed (Nov 2026). Negative tests were written first.
"""
import unittest

from sportsliveinfo import linking


def ev(eid, source, home, away, start="2026-11-14T15:00:00+00:00", **kw):
    row = {"id": eid, "source_id": source, "sport": "football", "participants": [home, away],
           "title": f"{home} v {away}", "start_utc": start, "start_precision": "scheduled"}
    row.update(kw)
    return row


def merged_count(a, b):
    return len(linking.merge_events([a, b]))


def pair(home1, away1, home2, away2, **kw):
    start2 = kw.pop("start2", "2026-11-14T15:00:00+00:00")
    comp2 = kw.pop("comp2", None)
    first = ev("a:1", "football_data", home1, away1, **kw)
    second = ev("b:1", "api_sports", home2, away2, start=start2, **({"competition_id": comp2} if comp2 else {}))
    return first, second


class FalseMergeTests(unittest.TestCase):
    def test_one_different_side_stays_separate(self):
        self.assertEqual(merged_count(*pair("Real Madrid", "Barcelona", "Real Betis", "Barcelona")), 2)

    def test_men_and_women_stay_separate(self):
        self.assertEqual(merged_count(*pair("Arsenal", "Chelsea", "Arsenal W", "Chelsea W")), 2)
        self.assertEqual(merged_count(*pair("Union Berlin", "Bayern", "Union Berlin Frauen", "Bayern Frauen")), 2)

    def test_reserve_and_youth_sides_stay_separate(self):
        self.assertEqual(merged_count(*pair("Real Madrid", "Getafe", "Real Madrid Castilla", "Getafe")), 2)
        self.assertEqual(merged_count(*pair("Bayern", "Union Berlin", "Bayern II", "Union Berlin")), 2)
        self.assertEqual(merged_count(*pair("Arsenal", "Chelsea", "Arsenal U21", "Chelsea")), 2)
        self.assertEqual(merged_count(*pair("Arsenal", "Chelsea", "Arsenal U19", "Chelsea")), 2)
        self.assertEqual(merged_count(*pair("Espanyol", "Getafe", "Espanyol Women", "Getafe")), 2)

    def test_same_teams_on_different_days_stay_separate(self):
        self.assertEqual(merged_count(*pair("Espanyol", "Getafe", "RCD Espanyol de Barcelona", "Getafe",
                                            start2="2026-11-15T15:00:00+00:00")), 2)

    def test_kickoffs_outside_fifteen_minutes_need_equal_names(self):
        self.assertEqual(merged_count(*pair("Espanyol", "Getafe", "RCD Espanyol de Barcelona", "Getafe",
                                            start2="2026-11-14T15:30:00+00:00")), 2)

    def test_different_competitions_stay_separate(self):
        self.assertEqual(merged_count(*pair("Espanyol", "Getafe", "RCD Espanyol de Barcelona", "Getafe",
                                            competition_id="fd:PD", comp2="fd:CDR")), 2)

    def test_founding_year_does_not_make_munich_clubs_one_team(self):
        self.assertFalse(linking.same_team(linking.team_key("TSV 1860 Munich"), linking.team_key("Bayern Munich")))
        self.assertFalse(linking.same_team(linking.team_key("Heidenheim 1846"), linking.team_key("Heidenheim 1900")))

    def test_low_signal_and_generic_words_do_not_anchor(self):
        self.assertEqual(merged_count(*pair("Arsenal", "North London", "Arsenal", "North Melbourne")), 2)


class NameFormMergeTests(unittest.TestCase):
    def assertMerges(self, home1, away1, home2, away2):
        self.assertEqual(merged_count(*pair(home1, away1, home2, away2)), 1, (home1, away1, home2, away2))

    def test_club_form_prefixes(self):
        self.assertMerges("Arminia Bielefeld", "Getafe", "DSC Arminia Bielefeld", "Getafe")
        self.assertMerges("Havelse", "Viktoria Köln", "TSV Havelse", "FC Viktoria Köln")
        self.assertMerges("Havelse v FC Viktoria Köln".split(" v ")[0], "FC Viktoria Köln",
                          "TSV Havelse", "Viktoria Köln")

    def test_founding_year_dropped(self):
        self.assertMerges("Darmstadt", "Heidenheim", "Darmstadt", "Heidenheim 1846")
        self.assertMerges("Heidenheim 1846", "Darmstadt", "Heidenheim", "Darmstadt")

    def test_contained_short_forms(self):
        self.assertMerges("Espanyol", "Getafe", "RCD Espanyol de Barcelona", "Getafe")
        self.assertMerges("Estac Troyes", "Getafe", "ES Troyes AC", "Getafe")
        self.assertMerges("Borussia Mönchengladbach", "Mainz", "Gladbach", "Mainz")

    def test_women_spellings(self):
        self.assertMerges("Union Berlin W", "Bayern W", "Union Berlin Frauen", "Bayern Frauen")
        self.assertMerges("Lyon Féminin", "PSG Féminin", "Lyon Women", "PSG Women")
        self.assertMerges("Bayern Damen", "Köln Damen", "Bayern Women", "Köln Women")

    def test_german_exonyms(self):
        self.assertMerges("1. FC Köln", "Mainz", "Cologne", "Mainz")
        self.assertMerges("FC Köln", "Mainz", "1. FC Köln", "Mainz")
        self.assertMerges("Nürnberg", "Mainz", "Nuremberg", "Mainz")
        self.assertMerges("Mönchengladbach", "Mainz", "Gladbach", "Mainz")

    def test_team_key_equalities(self):
        key = linking.team_key
        self.assertEqual(key("Union Berlin W"), key("Union Berlin Frauen"))
        self.assertEqual(key("Estac Troyes"), key("ES Troyes AC"))


if __name__ == "__main__":
    unittest.main()
