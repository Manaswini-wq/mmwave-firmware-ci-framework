#!/usr/bin/env perl
# regression_diff.pl - Compare regression results between two CI runs
# Loads two result files (CSV), identifies new failures, new passes,
# persistent failures, and generates a markdown diff report

use strict;
use warnings;
use Getopt::Long;
use POSIX qw(strftime);

my $baseline_file = '';
my $current_file  = '';
my $output_md     = 'reports/regression_diff.md';
my $fail_on_new   = 1;
my $help          = 0;

GetOptions(
    'baseline=s'   => \$baseline_file,
    'current=s'    => \$current_file,
    'output=s'     => \$output_md,
    'fail-on-new!' => \$fail_on_new,
    'help'         => \$help,
) or die "Error in command line arguments\n";

if ($help || !$baseline_file || !$current_file) {
    print "Usage: $0 --baseline FILE --current FILE [--output FILE] [--no-fail-on-new]\n";
    print "  Compares two regression result CSV files and generates a diff report.\n";
    print "  CSV format: test_name,status (PASS/FAIL/SKIP)\n";
    exit($help ? 0 : 1);
}

my $baseline = load_results($baseline_file);
my $current  = load_results($current_file);

my (@new_failures, @new_passes, @persistent_failures, @persistent_passes, @new_tests, @removed_tests);

# Classify each test
my %all_tests;
$all_tests{$_}++ for keys %$baseline;
$all_tests{$_}++ for keys %$current;

for my $test (sort keys %all_tests) {
    my $base_status = $baseline->{$test} || '';
    my $curr_status = $current->{$test}  || '';

    if (!$base_status && $curr_status) {
        push @new_tests, { name => $test, status => $curr_status };
    } elsif ($base_status && !$curr_status) {
        push @removed_tests, { name => $test, status => $base_status };
    } elsif ($base_status eq 'PASS' && $curr_status eq 'FAIL') {
        push @new_failures, $test;
    } elsif ($base_status eq 'FAIL' && $curr_status eq 'PASS') {
        push @new_passes, $test;
    } elsif ($base_status eq 'FAIL' && $curr_status eq 'FAIL') {
        push @persistent_failures, $test;
    } elsif ($base_status eq 'PASS' && $curr_status eq 'PASS') {
        push @persistent_passes, $test;
    }
}

# Generate markdown report
my $timestamp = strftime("%Y-%m-%d %H:%M:%S", localtime);
open my $fh, '>', $output_md or die "Cannot open $output_md: $!\n";

print $fh "# Regression Diff Report\n\n";
print $fh "**Generated:** $timestamp\n\n";
print $fh "| Category            | Count |\n";
print $fh "|---------------------|-------|\n";
printf $fh "| New Failures        | %d    |\n", scalar @new_failures;
printf $fh "| New Passes (Fixed)  | %d    |\n", scalar @new_passes;
printf $fh "| Persistent Failures | %d    |\n", scalar @persistent_failures;
printf $fh "| Stable Passes       | %d    |\n", scalar @persistent_passes;
printf $fh "| New Tests           | %d    |\n", scalar @new_tests;
printf $fh "| Removed Tests       | %d    |\n\n", scalar @removed_tests;

if (@new_failures) {
    print $fh "## New Failures\n\nThese tests passed in the baseline but now fail:\n\n";
    print $fh "| Test Name |\n|-----------|\n";
    printf $fh "| `%s` |\n", $_ for @new_failures;
    print $fh "\n";
}

if (@new_passes) {
    print $fh "## Newly Fixed Tests\n\nThese tests failed in the baseline and now pass:\n\n";
    print $fh "| Test Name |\n|-----------|\n";
    printf $fh "| `%s` |\n", $_ for @new_passes;
    print $fh "\n";
}

if (@persistent_failures) {
    print $fh "## Persistent Failures\n\nThese tests continue to fail:\n\n";
    printf $fh "- `%s`\n", $_ for @persistent_failures;
    print $fh "\n";
}

if (@new_tests) {
    print $fh "## New Tests\n\n";
    printf $fh "- `%s` (%s)\n", $_->{name}, $_->{status} for @new_tests;
    print $fh "\n";
}

close $fh;
printf "Regression diff written to %s\n", $output_md;
printf "  New failures: %d | New passes: %d | Persistent failures: %d\n",
    scalar @new_failures, scalar @new_passes, scalar @persistent_failures;

# Exit non-zero if new failures found and --fail-on-new is set
if ($fail_on_new && @new_failures) {
    printf STDERR "ERROR: %d new test failure(s) detected!\n", scalar @new_failures;
    exit 1;
}

exit 0;

# --- Subroutines ---

sub load_results {
    my ($path) = @_;
    my %results;
    open my $fh, '<', $path or die "Cannot open $path: $!\n";
    my $header = <$fh>;  # skip header
    while (<$fh>) {
        chomp;
        my @fields = split /,/, $_;
        next unless @fields >= 2;
        my $name   = $fields[0];
        my $status = uc($fields[1]);
        $status = 'PASS' if $status =~ /^pass/i;
        $status = 'FAIL' if $status =~ /^fail/i;
        $status = 'SKIP' if $status =~ /^skip/i;
        $results{$name} = $status;
    }
    close $fh;
    return \%results;
}
