/*
 *  GEM-Mapper v3 (GEM3)
 *  Copyright (c) 2011-2017 by Santiago Marco-Sola  <santiagomsola@gmail.com>
 *
 *  This file is part of GEM-Mapper v3 (GEM3).
 *
 *  This program is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * PROJECT: GEM-Mapper v3 (GEM3)
 * AUTHOR(S): Santiago Marco-Sola <santiagomsola@gmail.com>
 * DESCRIPTION:
 *   Filtering candidates module provides functions to verify filtering-regions
 *   against its corresponding region of text in the index and compute the
 *   distance of the alignment between both
 */

#include "filtering/candidates/filtering_candidates.h"
#include "align/pattern/pattern.h"

/*
 * Exact-Extend Candidates
 */
void filtering_candidates_extend_candidates(
    filtering_candidates_t* const filtering_candidates,
    pattern_t* const pattern,
    matches_t* const matches);
void filtering_candidates_extend_discarded_candidates(
    filtering_candidates_t* const filtering_candidates,
    pattern_t* const pattern,
    matches_t* const matches);

/*
 * Verify Candidates
 */
uint64_t filtering_candidates_verify_candidates(
    filtering_candidates_t* const filtering_candidates,
    pattern_t* const pattern,
    matches_t* const matches);

