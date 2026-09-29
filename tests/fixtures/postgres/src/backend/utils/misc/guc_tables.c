/* guc_tables.c: one integer setting for the fixture checks */
struct config_int ConfigureNamesInt[] =
{
	{
		{"example_size", PGC_POSTMASTER, STATS,
			gettext_noop("Sets the byte size of each slot."),
			NULL,
			GUC_UNIT_BYTE
		},
		&pgstat_example_size,
		1024, 100, 1048576,
		NULL, NULL, NULL
	},
};
