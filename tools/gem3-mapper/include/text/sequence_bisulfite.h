/*
 *  GEM-Mapper v3 (GEM3)
 *  Copyright (c) 2011-2017 by Santiago Marco-Sola  <santiagomsola@gmail.com>
 *  Copyright (c) 2011-2017 by Simon Heath  <simon.heath@gmail.com>
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
 *            Simon Heath <simon.heath@gmail.com>
 * DESCRIPTION:
 *   Mapper module provides support functions to bisulfite mode(s)
 */

#ifndef SEQUENCE_BISULFITE_H_
#define SEQUENCE_BISULFITE_H_

#include "utils/essentials.h"
#include "archive/search/archive_search.h"

bool sequence_bisulfite_check_cg_depletion_se(
    sequence_t* const read_sequence);
bool sequence_bisulfite_check_cg_depletion_pe(
    sequence_t* const read_sequence1,
    sequence_t* const read_sequence2);

#endif /* SEQUENCE_BISULFITE_H_ */
