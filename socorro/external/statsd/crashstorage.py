# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


from configman import RequiredConfig, Namespace, class_converter
from datetime import datetime


#------------------------------------------------------------------------------
def str_to_list(string_list):
    item_list = []
    for x in string_list.split(','):
        item_list.append(x.strip())
    return item_list


#==============================================================================
class StatsdCrashStorageBase(RequiredConfig):
    """This class is a duck typed crash storage class.  All it does is log
    the calls made to it to statsd.  It can use several different
    implementations of statsd client as specified by the 'statsd_module' and
    'statsd_module_incr_method_name' configuration parameters."""

    required_config = Namespace()
    required_config.add_option(
        'statsd_module',
        doc='the name of module that implements statsd client',
        default='datadog.statsd',
        reference_value_from='resource.statsd',
        from_string_converter=class_converter,
    )
    required_config.add_option(
        'statsd_host',
        doc='the hostname of statsd',
        default='',
        reference_value_from='resource.statsd',
    )
    required_config.add_option(
        'statsd_port',
        doc='the port number for statsd',
        default=8125,
        reference_value_from='resource.statsd',
    )
    required_config.add_option(
        'prefix',
        doc='a string to be used as the prefix for statsd names',
        default='save_processed',
        reference_value_from='resource.statsd',
    )

    #--------------------------------------------------------------------------
    def __init__(self, config, quit_check_callback=None):
        super(StatsdCrashStorageBase, self).__init__()
        self.config = config
        if config.prefix:
            self.prefix = config.prefix
        else:
            self.prefix = ''
        self.statsd = self.config.statsd_module.statsd(
            config.statsd_host,
            config.statsd_port,
        )

    #--------------------------------------------------------------------------
    def _make_name(self, *args):
        names =  [self.prefix] if self.prefix else []
        names.extend(list(args))
        return '.'.join(x for x in names if x)


#==============================================================================
class StatsdCrashStorage(StatsdCrashStorageBase):
    """This class is a duck typed crash storage class.  All it does is log
    the calls made to it to statsd.  It can use several different
    implementations of statsd client as specified by the 'statsd_module' and
    'statsd_module_incr_method_name' configuration parameters."""

    required_config = Namespace()
    required_config.add_option(
        'statsd_module_incr_method_name',
        doc='the name of method that implements increment',
        default='increment',
        reference_value_from='resource.statsd',
    )
    required_config.add_option(
        'active_counters_list',
        default='save_processed',
        doc='a comma delimeted list of counters',
        from_string_converter=str_to_list,
        reference_value_from='resource.statsd',
    )

    #--------------------------------------------------------------------------
    def __init__(self, config, quit_check_callback=None):
        super(StatsdCrashStorage, self).__init__(config, quit_check_callback)
        self.counter_increment = getattr(
            self.statsd,
            config.statsd_module_incr_method_name
        )

    #--------------------------------------------------------------------------
    def _incr(self, name):
        if (
            self.config.statsd_host
            and name in self.config.active_counters_list
        ):
            counter_name = self._make_name(name)
            self.counter_increment(counter_name)

    #--------------------------------------------------------------------------
    def __getattr__(self, attr):
        self._incr(attr)
        return self._dummy_do_nothing_method

    #--------------------------------------------------------------------------
    def _dummy_do_nothing_method(self, *args, **kwargs):
        pass


#==============================================================================
class StatsdBenchmarkingCrashStorage(StatsdCrashStorageBase):
    """a wrapper around crash stores that will benchmark the calls in the logs
    """
    required_config = Namespace()
    required_config.add_option(
        name="wrapped_crashstore",
        doc="another crash store to be benchmarked",
        default='',
        from_string_converter=class_converter
    )

    #--------------------------------------------------------------------------
    def __init__(self, config, quit_check_callback=None):
        super(StatsdBenchmarkingCrashStorage, self).__init__(
            config,
            quit_check_callback
        )
        self.wrapped_crashstore = config.wrapped_crashstore(
            config,
            quit_check_callback)
        self.start_timer = datetime.now
        self.end_timer = datetime.now
        self.prefixes = {}

    #--------------------------------------------------------------------------
    def close(self):
        """some implementations may need explicit closing."""
        self.wrapped_crashstore.close()

    #--------------------------------------------------------------------------
    def __getattr__(self, attr):
        # allow any AttributeError to propagate outward
        wrapped_method = getattr(self.wrapped_crashstore, attr)

        def benchmarker(*args,  **kwargs):
            start_time = self.start_timer()
            result = wrapped_method(*args, **kwargs)
            end_time = self.end_timer()
            self.statsd.timing(
                self.prefixes.get(
                    attr,
                    self._make_name(self.wrapped_crashstore.__name__, attr)
                ),
                (end_time - start_time).microseconds
            )
            return result

        return benchmarker

