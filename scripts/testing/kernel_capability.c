#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/landlock.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#if !defined(__x86_64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This reviewed probe is x86_64 little-endian only.
#endif

/* Source-only until root approves the exact build and first probe commands.
 * The trusted parent creates one fixture and forks one worker BEFORE restriction.
 * No candidate, Python, native extension, network traffic, or real spawn sample.
 */
enum { MAGIC = 0x43505242, VERSION = 1, ALL_CHECKS = (1u << 14) - 1 };
enum {
    S_SETUP = 1, S_BASELINE, S_ABI, S_RULE, S_LL_READ, S_LL_DENY,
    S_FILTER, S_SC_STATE, S_SC_READ, S_SC_DENY, S_DONE
};
struct report {
    uint32_t magic, version, stage, ok, error, abi, checks, seccomp_mode;
};
struct body {
    const char *name, *data;
    mode_t initial_mode;
    int fd;
    struct stat before;
};
static struct body files[] = {
    {"allowed.txt", "leased fixture bytes\n", 0444, -1, {0}},
    {"unleased.txt", "unleased fixture bytes\n", 0444, -1, {0}},
    {"write-target.txt", "unchanged writable fixture\n", 0600, -1, {0}}
};
static const char fixture_template[] =
    "/tmp/chronicler-kernel-capability-XXXXXX";
static const uint64_t floor_bytes = UINT64_C(3) * 1024 * 1024 * 1024;

static int same_file(const struct stat *a, const struct stat *b, int body_times)
{
    return S_ISREG(a->st_mode) && S_ISREG(b->st_mode) &&
        a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_nlink == 1 && b->st_nlink == 1 &&
        a->st_mode == b->st_mode && a->st_uid == b->st_uid &&
        a->st_gid == b->st_gid && a->st_size == b->st_size &&
        (!body_times ||
         (a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
          a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
          a->st_ctim.tv_sec == b->st_ctim.tv_sec &&
          a->st_ctim.tv_nsec == b->st_ctim.tv_nsec));
}

static int limits(void)
{
    struct rlimit as = {512u * 1024u * 1024u, 512u * 1024u * 1024u};
    struct rlimit cpu = {4, 30}, core = {0, 0};
    /* Hosted lifecycle reserves 760 KiB for each capture, within joint 2 MiB. */
    struct rlimit fsize = {760u * 1024u, 760u * 1024u};
    cpu_set_t available, one;
    if (setrlimit(RLIMIT_AS, &as) || setrlimit(RLIMIT_CPU, &cpu) ||
        setrlimit(RLIMIT_CORE, &core) || setrlimit(RLIMIT_FSIZE, &fsize) ||
        sched_getaffinity(0, sizeof available, &available)) return -1;
    CPU_ZERO(&one);
    for (int i = 0; i < CPU_SETSIZE; ++i) {
        if (CPU_ISSET(i, &available)) {
            CPU_SET(i, &one);
            return sched_setaffinity(0, sizeof one, &one);
        }
    }
    errno = EINVAL;
    return -1;
}

static int read_exact_body(int fd, const char *body)
{
    char buffer[64];
    size_t size = strlen(body);
    ssize_t n = pread(fd, buffer, sizeof buffer, 0);
    return size < sizeof buffer && n == (ssize_t)size &&
        memcmp(buffer, body, size) == 0;
}

static int make_fixture(char *path, int *directory)
{
    struct statvfs space;
    if (statvfs("/tmp", &space) ||
        (uint64_t)space.f_bavail * space.f_frsize < floor_bytes + 524288) {
        errno = ENOSPC;
        return -1;
    }
    memcpy(path, fixture_template, sizeof fixture_template);
    if (!mkdtemp(path)) return -1;
    *directory = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (*directory < 0) return -1;
    for (size_t i = 0; i < sizeof files / sizeof files[0]; ++i) {
        int fd = openat(*directory, files[i].name,
            O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (fd < 0) return -1;
        files[i].fd = fd;  /* Retain partial creation for readonly closure. */
        size_t size = strlen(files[i].data);
        if (write(fd, files[i].data, size) != (ssize_t)size ||
            fchmod(fd, files[i].initial_mode) || fsync(fd) ||
            fstat(fd, &files[i].before) ||
            !S_ISREG(files[i].before.st_mode) ||
            files[i].before.st_nlink != 1 || !read_exact_body(fd, files[i].data))
            return -1;
    }
    return 0;
}

static _Noreturn void finish(struct report *r, int ok)
{
    r->ok = (uint32_t)ok;
    if (!ok) r->error = (uint32_t)errno;
    /* One fixed-size, atomic status write. No child diagnostic strings. */
    (void)syscall(SYS_write, 3, r, sizeof *r);
    (void)syscall(SYS_exit_group, ok ? 0 : 2);
    for (;;) { }
}

static void require(int condition, struct report *r)
{
    if (!condition) finish(r, 0);
}

static int denied_open(const char *path, int flags, int expected)
{
    int fd = (int)syscall(SYS_openat, AT_FDCWD, path, flags | O_CLOEXEC, 0);
    int observed = errno;
    if (fd >= 0) (void)syscall(SYS_close, fd);
    errno = observed;
    return fd == -1 && observed == expected;
}

static int raw_read_body(const char *path, int keep)
{
    char buffer[64];
    int fd = (int)syscall(SYS_openat, AT_FDCWD, path, O_RDONLY | O_CLOEXEC, 0);
    if (fd < 0) return -1;
    ssize_t n = syscall(SYS_read, fd, buffer, sizeof buffer);
    if (n != (ssize_t)strlen(files[0].data) ||
        memcmp(buffer, files[0].data, strlen(files[0].data))) {
        (void)syscall(SYS_close, fd);
        errno = EIO;
        return -1;
    }
    if (!keep) (void)syscall(SYS_close, fd);
    return keep ? fd : 0;
}

#define SC_ALLOW(n) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (n), 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
#define SC_DENY(n) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (n), 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM)
#define ARG_LO(n) (offsetof(struct seccomp_data, args[(n)]))
#define ARG_HI(n) (offsetof(struct seccomp_data, args[(n)]) + 4)

static int install_filter(void)
{
    const uint32_t writing = O_WRONLY | O_RDWR | O_CREAT | O_TRUNC |
        O_APPEND | O_TMPFILE;
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000u, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        /* write: only the one inherited status pipe, descriptor 3. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_write, 0, 6),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARG_HI(0)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARG_LO(0)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 3, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        /* openat: read flags only; Landlock still decides pathname access. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_openat, 0, 6),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARG_HI(2)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARG_LO(2)),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, writing, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        /* prctl: read back only the two installed restriction states. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_prctl, 0, 7),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARG_HI(0)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 4),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARG_LO(0)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, PR_GET_NO_NEW_PRIVS, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, PR_GET_SECCOMP, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        SC_DENY(SYS_socket), SC_DENY(SYS_socketpair), SC_DENY(SYS_connect),
        SC_DENY(SYS_accept), SC_DENY(SYS_accept4), SC_DENY(SYS_bind),
        SC_DENY(SYS_listen), SC_DENY(SYS_sendto), SC_DENY(SYS_sendmsg),
        SC_DENY(SYS_recvfrom), SC_DENY(SYS_recvmsg), SC_DENY(SYS_shutdown),
        SC_DENY(SYS_fork), SC_DENY(SYS_vfork), SC_DENY(SYS_clone),
        SC_DENY(SYS_clone3), SC_DENY(SYS_execve), SC_DENY(SYS_execveat),
        SC_ALLOW(SYS_read), SC_ALLOW(SYS_close), SC_ALLOW(SYS_fstat),
        SC_ALLOW(SYS_rt_sigreturn), SC_ALLOW(SYS_exit), SC_ALLOW(SYS_exit_group),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS)
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof filter / sizeof filter[0]),
        .filter = filter
    };
    return (int)syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, 0, &program);
}

static _Noreturn void worker(pid_t parent, int output, const char paths[3][256])
{
    struct report r = {MAGIC, VERSION, S_SETUP, 0, 0, 0, 0, 0};
    struct rlimit cpu = {20, 20};
    struct stat pipe_stat;
    if (output != 3 && dup3(output, 3, O_CLOEXEC) != 3) _exit(2);
    (void)close(0); (void)close(1); (void)close(2);
    require(syscall(SYS_close_range, 4u, ~0u, 0u) == 0 &&
        fstat(3, &pipe_stat) == 0 && S_ISFIFO(pipe_stat.st_mode) &&
        (fcntl(3, F_GETFL) & O_ACCMODE) == O_WRONLY &&
        setrlimit(RLIMIT_CPU, &cpu) == 0 &&
        prctl(PR_SET_PDEATHSIG, SIGKILL) == 0 && getppid() == parent &&
        prctl(PR_GET_SECCOMP, 0, 0, 0, 0) == 0, &r);

    r.stage = S_BASELINE;
    for (int i = 1; i <= 2; ++i) {
        int fd = open(paths[i], (i == 1 ? O_RDONLY : O_WRONLY) | O_CLOEXEC);
        require(fd >= 0, &r);
        require(close(fd) == 0, &r);
    }
    int socket_fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    require(socket_fd >= 0 && close(socket_fd) == 0, &r);
    errno = 0;
    require(syscall(SYS_clone3, NULL, 0) == -1 &&
        (errno == EINVAL || errno == EFAULT || errno == ENOSYS), &r);
    /* An empty executable name cannot name an executable, even if a filter
     * defect lets the syscall reach normal kernel argument/path validation. */
    char *const argv[] = {(char *)"", NULL};
    char *const env[] = {NULL};
    require(syscall(SYS_execve, "", argv, env) == -1 && errno == ENOENT, &r);
    r.checks |= 1u << 0;

    r.stage = S_ABI;
    long abi = syscall(SYS_landlock_create_ruleset, NULL, 0,
        LANDLOCK_CREATE_RULESET_VERSION);
    if (abi >= 0) r.abi = (uint32_t)abi;
    require(abi >= 3, &r);
    r.checks |= 1u << 1;
    require(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0 &&
        prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1, &r);

    r.stage = S_RULE;
    struct landlock_ruleset_attr rules = {.handled_access_fs = (1ULL << 15) - 1};
    int ruleset = (int)syscall(SYS_landlock_create_ruleset, &rules,
        sizeof rules.handled_access_fs, 0);
    require(ruleset >= 0, &r);
    int leased = open(paths[0], O_PATH | O_NOFOLLOW | O_CLOEXEC);
    struct stat leased_stat;
    require(leased >= 0 && fstat(leased, &leased_stat) == 0 &&
        same_file(&files[0].before, &leased_stat, 1), &r);
    struct landlock_path_beneath_attr rule = {
        .allowed_access = LANDLOCK_ACCESS_FS_READ_FILE, .parent_fd = leased
    };
    require(syscall(SYS_landlock_add_rule, ruleset, LANDLOCK_RULE_PATH_BENEATH,
        &rule, 0) == 0 &&
        syscall(SYS_landlock_restrict_self, ruleset, 0) == 0 &&
        close(leased) == 0 && close(ruleset) == 0, &r);
    r.checks |= 1u << 2;

    r.stage = S_LL_READ;
    require(raw_read_body(paths[0], 0) == 0, &r);
    r.checks |= 1u << 3;
    r.stage = S_LL_DENY;
    require(denied_open(paths[1], O_RDONLY, EACCES), &r);
    r.checks |= 1u << 4;
    require(denied_open(paths[2], O_WRONLY, EACCES), &r);
    r.checks |= 1u << 5;

    r.stage = S_FILTER;
    require(install_filter() == 0, &r);
    r.checks |= 1u << 6;
    r.stage = S_SC_STATE;
    long mode = syscall(SYS_prctl, PR_GET_SECCOMP, 0, 0, 0, 0);
    if (mode >= 0) r.seccomp_mode = (uint32_t)mode;
    require(mode == 2 &&
        syscall(SYS_prctl, PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1, &r);
    r.checks |= 1u << 7;
    r.stage = S_SC_READ;
    int read_fd = raw_read_body(paths[0], 1);
    require(read_fd >= 0, &r);
    r.checks |= 1u << 8;
    r.stage = S_SC_DENY;
    require(denied_open(paths[1], O_RDONLY, EACCES), &r);
    r.checks |= 1u << 9;
    require(denied_open(paths[2], O_WRONLY, EPERM), &r);
    require(syscall(SYS_write, read_fd, "x", 1) == -1 && errno == EPERM, &r);
    require(syscall(SYS_close, read_fd) == 0, &r);
    r.checks |= 1u << 10;
    require(syscall(SYS_socket, AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0) == -1 &&
        errno == EPERM, &r);
    r.checks |= 1u << 11;
    require(syscall(SYS_clone3, NULL, 0) == -1 && errno == EPERM, &r);
    r.checks |= 1u << 12;
    require(syscall(SYS_execve, "", argv, env) == -1 && errno == EPERM, &r);
    r.checks |= 1u << 13;
    r.stage = S_DONE;
    require(r.checks == ALL_CHECKS, &r);
    finish(&r, 1);
}

/* Verify the only three directory entries with raw getdents64, without creating
 * a stdio directory stream or allowing any worker directory-listing permission.
 */
struct entry64 {
    uint64_t ino;
    int64_t off;
    unsigned short reclen;
    unsigned char type;
    char name[];
};
static int exact_namespace(int directory)
{
    _Alignas(struct entry64) char buffer[1024];
    unsigned seen = 0;
    if (lseek(directory, 0, SEEK_SET) < 0) return 0;
    for (;;) {
        long length = syscall(SYS_getdents64, directory, buffer, sizeof buffer);
        if (length < 0) return 0;
        if (!length) break;
        for (long p = 0; p < length;) {
            struct entry64 *e = (struct entry64 *)(void *)(buffer + p);
            if (length - p < (long)offsetof(struct entry64, name) + 1 ||
                e->reclen < offsetof(struct entry64, name) + 1 ||
                e->reclen > length - p ||
                !memchr(e->name, 0, e->reclen - offsetof(struct entry64, name)))
                return 0;
            if (strcmp(e->name, ".") && strcmp(e->name, "..")) {
                unsigned match = 0;
                for (unsigned i = 0; i < 3; ++i)
                    if (!strcmp(e->name, files[i].name)) match = 1u << i;
                if (!match || (seen & match)) return 0;
                seen |= match;
            }
            p += e->reclen;
        }
    }
    return seen == 7;
}

static int readonly_closure(int directory, const char *fixture,
    const struct stat *dir_before)
{
    int ok = directory >= 0;
    struct stat now, path;
    if (!ok) return 0;
    if (fstat(directory, &now) || lstat(fixture, &path) ||
        !S_ISDIR(now.st_mode) || !S_ISDIR(path.st_mode) ||
        now.st_dev != dir_before->st_dev || now.st_ino != dir_before->st_ino ||
        path.st_dev != now.st_dev || path.st_ino != now.st_ino ||
        now.st_mode != path.st_mode || now.st_uid != dir_before->st_uid ||
        now.st_gid != dir_before->st_gid || now.st_nlink != 2 ||
        path.st_nlink != now.st_nlink || now.st_uid != getuid() ||
        now.st_mtim.tv_sec != dir_before->st_mtim.tv_sec ||
        now.st_mtim.tv_nsec != dir_before->st_mtim.tv_nsec ||
        now.st_ctim.tv_sec != dir_before->st_ctim.tv_sec ||
        now.st_ctim.tv_nsec != dir_before->st_ctim.tv_nsec ||
        (now.st_mode & 07777) != 0700 || !exact_namespace(directory)) ok = 0;
    for (unsigned i = 0; i < 3; ++i) {
        if (files[i].fd < 0) { ok = 0; continue; }
        if (fstat(files[i].fd, &now) ||
            fstatat(directory, files[i].name, &path, AT_SYMLINK_NOFOLLOW) ||
            !same_file(&files[i].before, &now, 1) ||
            !same_file(&now, &path, 1) ||
            !read_exact_body(files[i].fd, files[i].data)) ok = 0;
        if (fchmod(files[i].fd, 0444) || fstat(files[i].fd, &now) ||
            (now.st_mode & 07777) != 0444 || now.st_nlink != 1) ok = 0;
    }
    if (fchmod(directory, 0555) || fstat(directory, &now) ||
        lstat(fixture, &path) || !S_ISDIR(path.st_mode) ||
        path.st_dev != now.st_dev || path.st_ino != now.st_ino ||
        path.st_mode != now.st_mode || (now.st_mode & 07777) != 0555) ok = 0;
    return ok;
}

static double seconds(const struct timespec *t)
{
    return (double)t->tv_sec + (double)t->tv_nsec / 1e9;
}

int main(int argc, char **argv)
{
    (void)argv;
    umask(077);
    char fixture[sizeof fixture_template] = "";
    char paths[3][256];
    int directory = -1, pipes[2] = {-1, -1}, status = -1, error = 0;
    int waited = 0, timed_out = 0, closure = 0, parent_setup = 0;
    struct stat dir_before = {0};
    struct report report = {0};
    struct rusage usage = {0};
    struct timespec start, now;
    pid_t child = -1, parent = getpid();
    unsigned char wire[sizeof report + 1];
    size_t received = 0;
    clock_gettime(CLOCK_MONOTONIC, &start);
    if (argc != 1 || fcntl(0, F_GETFD) < 0 || fcntl(1, F_GETFD) < 0 ||
        fcntl(2, F_GETFD) < 0 || limits() || make_fixture(fixture, &directory) ||
        fstat(directory, &dir_before)) { error = errno ? errno : EINVAL; goto done; }
    for (int i = 0; i < 3; ++i) {
        const char *name = files[i].name;
        int n = snprintf(paths[i], sizeof paths[i], "%s/%s", fixture, name);
        if (n < 0 || (size_t)n >= sizeof paths[i]) { error = EOVERFLOW; goto done; }
    }
    if (pipe2(pipes, O_CLOEXEC | O_NONBLOCK)) { error = errno; goto done; }
    child = fork();
    if (child < 0) { error = errno; goto done; }
    if (!child) worker(parent, pipes[1], paths);
    parent_setup = 1;
    (void)close(pipes[1]); pipes[1] = -1;
    struct rlimit parent_cpu = {4, 4};
    if (setrlimit(RLIMIT_CPU, &parent_cpu)) { error = errno; goto terminate; }
    for (;;) {
        ssize_t n = read(pipes[0], wire + received, sizeof wire - received);
        if (n > 0) received += (size_t)n;
        else if (n < 0 && errno != EAGAIN && errno != EINTR) { error = errno; break; }
        pid_t result = wait4(child, &status, WNOHANG, &usage);
        if (result == child) { waited = 1; break; }
        if (result < 0 && errno != EINTR) { error = errno; break; }
        clock_gettime(CLOCK_MONOTONIC, &now);
        if (seconds(&now) - seconds(&start) >= 100) { timed_out = 1; break; }
        struct pollfd pending = {.fd = pipes[0], .events = POLLIN | POLLHUP};
        (void)poll(&pending, 1, 10);
    }
terminate:
    if (!waited) {
        (void)kill(child, SIGKILL);
        pid_t reaped;
        do { reaped = wait4(child, &status, 0, &usage); }
        while (reaped < 0 && errno == EINTR);
        waited = reaped == child;
    }
    if (received < sizeof wire) {
        ssize_t n = read(pipes[0], wire + received, sizeof wire - received);
        if (n > 0) received += (size_t)n;
    }
    if (received == sizeof report) memcpy(&report, wire, sizeof report);
done:
    if (directory >= 0) closure = readonly_closure(directory, fixture, &dir_before);
    clock_gettime(CLOCK_MONOTONIC, &now);
    struct rusage own = {0};
    (void)getrusage(RUSAGE_SELF, &own);
    double cpu = own.ru_utime.tv_sec + own.ru_utime.tv_usec / 1e6 +
        own.ru_stime.tv_sec + own.ru_stime.tv_usec / 1e6 +
        usage.ru_utime.tv_sec + usage.ru_utime.tv_usec / 1e6 +
        usage.ru_stime.tv_sec + usage.ru_stime.tv_usec / 1e6;
    int pass = !error && parent_setup && waited && !timed_out && closure &&
        WIFEXITED(status) && WEXITSTATUS(status) == 0 &&
        received == sizeof report && report.magic == MAGIC &&
        report.version == VERSION && report.ok == 1 && report.stage == S_DONE &&
        report.abi >= 3 && report.seccomp_mode == 2 && report.checks == ALL_CHECKS &&
        cpu <= 30 && seconds(&now) - seconds(&start) < 110;
    /* The generated fixture spelling is fixed printable ASCII, not input data. */
    printf("{\"kind\":\"C_FIXTURE_KERNEL_CAPABILITY_V1\",\"pass\":%s,"
        "\"fixture\":\"%s\",\"readonly_closure\":%s,\"parent_errno\":%d,"
        "\"worker_stage\":%u,\"worker_last_errno\":%u,\"landlock_abi\":%u,"
        "\"seccomp_mode\":%u,\"checks\":%u,\"expected_checks\":%u,"
        "\"status_bytes\":%zu,\"child_exit\":%d,\"child_signal\":%d,"
        "\"timed_out\":%s,\"wall_seconds\":%.6f,\"cpu_seconds\":%.6f,"
        "\"installed_candidate_qualified\":false}\n",
        pass ? "true" : "false", fixture, closure ? "true" : "false", error,
        report.stage, report.error, report.abi, report.seccomp_mode, report.checks,
        (unsigned)ALL_CHECKS, received,
        waited && WIFEXITED(status) ? WEXITSTATUS(status) : -1,
        waited && WIFSIGNALED(status) ? WTERMSIG(status) : 0,
        timed_out ? "true" : "false", seconds(&now) - seconds(&start), cpu);
    return pass ? 0 : 2;
}
