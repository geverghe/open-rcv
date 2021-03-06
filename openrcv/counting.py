#
# Copyright (c) 2014 Chris Jerdonek. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#

"""Support for counting ballots."""

import logging
import os
import string

# This module should not import the module containing the JSON objects.
# In particular, it should not use any of the JSON object classes.  There
# are two reasons for this: (1) it avoids circular dependencies, and
# (2) for simplicity, the counting algorithms should be decoupled from
# and not depend on serialization, etc.  Serialization is supplemental
# to any counting and not a prerequisite.
# TODO: move some of the above comments to the module docstring.

from openrcv import models
from openrcv.formats.internal import parse_internal_ballot, to_internal_ballot
from openrcv.models import ContestResults, RoundResults
from openrcv.parsing import BLTParser, Parser


log = logging.getLogger(__name__)


def any_value(dict_):
    """Return any value in dict."""
    try:
        return next(iter(dict_.values()))
    except StopIteration:
        raise ValueError("dict has no values")


def get_majority(total):
    """Return the majority threshold for a single-winner election.

    Note that this returns 1 for a 0 total.
    """
    return total // 2 + 1


def get_winner(totals):
    """Return the candidate with a majority, or None.

    Arguments:
      totals: dict of candidate to vote total.
    """
    total = sum(totals.values())
    threshold = get_majority(total)
    for candidate, candidate_total in totals.items():
        if candidate_total >= threshold:
            return candidate
    return None


def get_lowest(totals):
    """Return which candidate to eliminate.

    Raises a NotImplementedError if there is a tie.
    """
    lowest_total = any_value(totals)
    lowest_candidates = set()
    for candidate, total in totals.items():
        if total < lowest_total:
            lowest_total = total
            lowest_candidates = set((candidate,))
        elif total == lowest_total:
            lowest_candidates.add(candidate)
    return lowest_candidates


# TODO: remove this method.
def count_irv_contest(contest):
    """Tabulate a contest using IRV, and return a ContestResults object.

    Arguments:
      contest: a ContestInput object.
    """
    # TODO: handle case of 0 total (no winner, probably)?  And add a test case.
    # TODO: add tests for degenerate cases (0 candidates, 1 candidate, 0 votes, etc).
    tabulator = Tabulator(contest)
    return tabulator.count()



class Tabulator(object):

    def __init__(self, contest):
        self.contest = contest

    def count_ballots(self, candidate_numbers):
        """Count one round, and return a RoundResults object.

        Arguments:
          candidate_numbers: a set of candidates eligible to receive votes.
        """
        totals = {}
        for candidate_number in candidate_numbers:
            totals[candidate_number] = 0

        with self.contest.ballots_resource.reading() as ballots:
            for weight, choices in ballots:
                # TODO: replace with call to self.count_ballot().
                for choice in choices:
                    if choice in candidate_numbers:
                        totals[choice] += weight
                        break

        return totals

    def count(self):
        contest = self.contest
        candidates_info = contest.make_candidates_info()
        candidate_numbers = set(self.contest.get_candidate_numbers())
        outcome = models.ContestOutcome()
        rounds = []
        while True:
            # TODO: move more of the logic below into Tabulator.
            #  In particular, the tabulator should be responsible for setting
            #  all of the attributes on the round object.
            totals = self.count_ballots(candidate_numbers)
            round_results = RoundResults(candidates_info=candidates_info, totals=totals)
            rounds.append(round_results)
            totals = round_results.totals
            winner = get_winner(totals)
            if winner is not None:
                round_results.elected = [winner]
                break
            last_place = get_lowest(totals)
            if len(last_place) > 1:
                # Then there is a tie.
                outcome.tied_last_place = last_place
                break

            candidate_numbers -= last_place

        outcome.last_round = len(rounds)
        results = ContestResults(outcome=outcome, rounds=rounds)
        return results
