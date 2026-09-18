import * as mock from './mock'
import * as real from './real'

const USE_MOCK = true

export const listTables = USE_MOCK ? mock.listTables : real.listTables
export const runQuery = USE_MOCK ? mock.runQuery : real.runQuery
